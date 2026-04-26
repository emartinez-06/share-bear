import logging
from urllib.parse import quote

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponseForbidden, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from .forms import AIQuoteForm, BookingLinkForm, QuoteVideoForm
from .gemini_quote import build_quote_prompt, format_share_bear_offer_display, get_quote_from_gemini
from .models import AIQuote
from .supabase_storage import create_signed_video_url, is_storage_configured, upload_quote_video
from .video_utils import file_extension_for_upload

logger = logging.getLogger(__name__)

# Shown on /ai-quote/dev-success/ when DEBUG is True (no Gemini call).
DEV_MOCK_QUOTE_ITEM_NAME = 'Sample item (dev preview)'
DEV_MOCK_OFFER_DISPLAY = '$127'


def home_view(request):
    return render(
        request,
        'index.html',
        {'vercel_analytics_enabled': settings.VERCEL_ANALYTICS_ENABLED},
    )


def ai_quote_dev_success_view(request):
    """DEBUG-only: render the quote success page with a fixed offer (no API)."""
    if not settings.DEBUG:
        raise Http404()
    return render(
        request,
        'ai_quote_success.html',
        {
            'item_name': DEV_MOCK_QUOTE_ITEM_NAME,
            'offer_display': DEV_MOCK_OFFER_DISPLAY,
            'vercel_analytics_enabled': settings.VERCEL_ANALYTICS_ENABLED,
            'dev_preview': True,
            'quote': None,
            'video_upload_configured': is_storage_configured(),
            'show_confetti': True,
            'quote_video_max_mb': settings.QUOTE_VIDEO_MAX_BYTES // (1024 * 1024),
        },
    )


def admin_quotes_view(request):
    if not request.user.is_authenticated:
        return redirect(f"{settings.LOGIN_URL}?next={quote(request.path)}")
    if not (request.user.is_staff or request.user.is_superuser):
        return HttpResponseForbidden('You do not have access to this page.')

    quotes = list(
        AIQuote.objects.select_related('user').all().order_by('-created_at')[:200]
    )
    for q in quotes:
        q.signed_video_url = None
        if q.has_video and q.video_path:
            q.signed_video_url = create_signed_video_url(q.video_path, expires_in=1200)
    return render(
        request,
        'admin_quotes.html',
        {
            'quotes': quotes,
            'vercel_analytics_enabled': settings.VERCEL_ANALYTICS_ENABLED,
        },
    )


@require_http_methods(['POST'])
def admin_accept_quote_view(request, quote_id: int):
    if not request.user.is_authenticated:
        return redirect(f"{settings.LOGIN_URL}?next={quote(request.path)}")
    if not (request.user.is_staff or request.user.is_superuser):
        return HttpResponseForbidden('You do not have access to this page.')

    quote = get_object_or_404(AIQuote, pk=quote_id)
    if not quote.has_video:
        messages.error(
            request,
            'This quote has no video yet—ask the user to upload from their quote page.',
        )
        return redirect('admin_quotes')
    if quote.quote_accepted_by_admin:
        messages.info(request, 'This offer was already accepted.')
        return redirect('admin_quotes')
    quote.quote_accepted_by_admin = True
    quote.quote_reviewed_at = timezone.now()
    quote.save(update_fields=['quote_accepted_by_admin', 'quote_reviewed_at'])
    messages.success(
        request,
        f'You accepted the buy-back offer for @{quote.user.username} — {quote.item_name}.',
    )
    return redirect('admin_quotes')


def ai_quote_view(request):
    if request.method == 'POST':
        form = AIQuoteForm(request.POST)
        if form.is_valid():
            data = form.cleaned_data
            if data.get('unknown_make_model'):
                make = ''
                model = ''
            else:
                make = data.get('make', '').strip()
                model = data.get('model', '').strip()
            prompt = build_quote_prompt(
                item_name=data['item_name'],
                description=data['description'],
                make=make,
                model=model,
                unknown_make_model=bool(data.get('unknown_make_model')),
            )
            try:
                quote_text = get_quote_from_gemini(prompt)
            except Exception as e:
                logger.exception('Gemini quote failed')
                return render(
                    request,
                    'ai_quote.html',
                    {
                        'form': form,
                        'vercel_analytics_enabled': settings.VERCEL_ANALYTICS_ENABLED,
                        'dev_success_preview': settings.DEBUG,
                        'gemini_error': str(e) or 'Could not get a quote right now. Try again later.',
                    },
                )
            if request.user.is_authenticated:
                q = AIQuote.objects.create(
                    user=request.user,
                    item_name=data['item_name'],
                    description=data['description'],
                    make=make,
                    model=model,
                    unknown_make_model=bool(data.get('unknown_make_model')),
                    quote_text=quote_text,
                )
                success_url = reverse('ai_quote_success_detail', kwargs={'quote_id': q.pk})
                return HttpResponseRedirect(f'{success_url}?celebrate=1')
            return render(
                request,
                'ai_quote_success.html',
                {
                    'item_name': data['item_name'],
                    'offer_display': format_share_bear_offer_display(quote_text),
                    'vercel_analytics_enabled': settings.VERCEL_ANALYTICS_ENABLED,
                    'dev_preview': False,
                    'quote': None,
                    'video_upload_configured': is_storage_configured(),
                    'show_confetti': True,
                    'quote_video_max_mb': settings.QUOTE_VIDEO_MAX_BYTES // (1024 * 1024),
                },
            )
    else:
        form = AIQuoteForm()
    return render(
        request,
        'ai_quote.html',
        {
            'form': form,
            'vercel_analytics_enabled': settings.VERCEL_ANALYTICS_ENABLED,
            'dev_success_preview': settings.DEBUG,
        },
    )


@login_required
@require_http_methods(['GET', 'HEAD', 'POST'])
def ai_quote_success_detail_view(request, quote_id: int):
    """Quote success / acceptance page for a stored AI quote (signed-in only)."""
    quote = get_object_or_404(AIQuote, pk=quote_id, user=request.user)
    if request.method == 'POST':
        form = BookingLinkForm(request.POST)
        if form.is_valid():
            link = form.cleaned_data['booking_link'].strip()
            if link:
                quote.booking_link = link
                quote.save(update_fields=['booking_link'])
                messages.success(request, 'Booking link saved.')
        return redirect('ai_quote_success_detail', quote_id=quote.pk)
    form = BookingLinkForm(initial={'booking_link': quote.booking_link})
    celebrate = request.GET.get('celebrate') in ('1', 'true', 'yes')
    return render(
        request,
        'ai_quote_success.html',
        {
            'item_name': quote.item_name,
            'offer_display': quote.offer_display,
            'vercel_analytics_enabled': settings.VERCEL_ANALYTICS_ENABLED,
            'dev_preview': False,
            'quote': quote,
            'booking_link_form': form,
            'video_upload_configured': is_storage_configured(),
            'show_confetti': celebrate,
            'quote_video_max_mb': settings.QUOTE_VIDEO_MAX_BYTES // (1024 * 1024),
        },
    )


@login_required
@require_http_methods(['POST'])
def quote_video_upload_view(request, quote_id: int):
    quote = get_object_or_404(AIQuote, pk=quote_id, user=request.user)
    if quote.quote_accepted_by_admin:
        messages.info(request, 'This offer is already confirmed by SHARE Bear.')
        return redirect('ai_quote_success_detail', quote_id=quote.pk)

    form = QuoteVideoForm(
        request.POST,
        request.FILES,
        max_bytes=settings.QUOTE_VIDEO_MAX_BYTES,
    )
    if not form.is_valid():
        err = form.errors.get('video') or form.errors.get('__all__', ['Invalid upload.'])
        messages.error(request, err[0] if err else 'Invalid upload.')
        return redirect('ai_quote_success_detail', quote_id=quote.pk)

    if not is_storage_configured():
        messages.error(
            request,
            'Video upload is not configured. Please try again later or contact support.',
        )
        return redirect('ai_quote_success_detail', quote_id=quote.pk)

    video = form.cleaned_data['video']
    data = video.read()
    ext = file_extension_for_upload(getattr(video, 'name', '') or '')
    object_path = f'{request.user.pk}/quote_{quote.pk}/current{ext}'
    try:
        upload_quote_video(
            file_bytes=data,
            object_path=object_path,
            content_type=video.content_type or 'application/octet-stream',
        )
    except RuntimeError as e:
        messages.error(request, str(e) or 'Upload failed. Try a smaller file or a different format.')
        return redirect('ai_quote_success_detail', quote_id=quote.pk)

    quote.has_video = True
    quote.video_path = object_path
    quote.save(update_fields=['has_video', 'video_path'])
    messages.success(
        request,
        "Video received. Your offer is pending review—SHARE Bear will confirm once we've watched it.",
    )
    return redirect('ai_quote_success_detail', quote_id=quote.pk)


def admin_kanban_view(request):
    if not request.user.is_authenticated:
        return redirect(f"{settings.LOGIN_URL}?next={quote(request.path)}")
    if not (request.user.is_staff or request.user.is_superuser):
        return HttpResponseForbidden('You do not have access to this page.')

    all_quotes = list(AIQuote.objects.select_related('user').order_by('-created_at'))
    awaiting, approved, picked_up_list = [], [], []
    for q in all_quotes:
        q.signed_video_url = None
        if q.has_video and q.video_path:
            q.signed_video_url = create_signed_video_url(q.video_path, expires_in=1200)
        if q.picked_up:
            picked_up_list.append(q)
        elif q.quote_accepted_by_admin:
            approved.append(q)
        else:
            awaiting.append(q)
    return render(
        request,
        'admin_kanban.html',
        {
            'awaiting': awaiting,
            'approved': approved,
            'picked_up': picked_up_list,
            'vercel_analytics_enabled': settings.VERCEL_ANALYTICS_ENABLED,
        },
    )


@require_http_methods(['POST'])
def admin_kanban_approve_view(request, quote_id: int):
    if not request.user.is_authenticated:
        return redirect(f"{settings.LOGIN_URL}?next={quote(request.path)}")
    if not (request.user.is_staff or request.user.is_superuser):
        return HttpResponseForbidden('You do not have access to this page.')
    messages.info(request, 'Approve action coming soon — no changes made.')
    return redirect('admin_kanban')


@require_http_methods(['POST'])
def admin_kanban_pickup_view(request, quote_id: int):
    if not request.user.is_authenticated:
        return redirect(f"{settings.LOGIN_URL}?next={quote(request.path)}")
    if not (request.user.is_staff or request.user.is_superuser):
        return HttpResponseForbidden('You do not have access to this page.')
    messages.info(request, 'Mark as Picked Up coming soon — no changes made.')
    return redirect('admin_kanban')
