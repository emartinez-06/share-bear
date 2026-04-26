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

from .forms import AdminAcceptQuoteForm, AIQuoteForm, BookingLinkForm, QuoteVideoForm
from .gemini_quote import build_quote_prompt, format_share_bear_offer_display, get_quote_from_gemini
from .models import AIQuote
from .supabase_storage import create_signed_video_url, is_storage_configured, upload_quote_video
from .video_utils import file_extension_for_upload, video_mime_type_from_path

logger = logging.getLogger(__name__)

# Shown on /ai-quote/dev-success/ when DEBUG is True (no Gemini call).
DEV_MOCK_QUOTE_ITEM_NAME = 'Sample item (dev preview)'
DEV_MOCK_OFFER_DISPLAY = '$127'


def build_approval_mailto_url(quote_obj: AIQuote) -> str | None:
    recipient = (quote_obj.user.email or '').strip()
    if not recipient:
        return None

    subject = f'Your SHARE Bear item has been approved: {quote_obj.item_name}'
    body_lines = [
        f'Hi {quote_obj.user.first_name or quote_obj.user.username},',
        '',
        'Your item has been approved!',
        'Please fill out the booking link found under your account profile to schedule a pickup date convenient for you.',
        '',
        f'Final approved price: {quote_obj.offer_display}',
        f'Item: {quote_obj.item_name}',
        f'Item description: {quote_obj.description}',
        '',
        'If anything seems out of the ordinary or you have any concerns, please reply directly to this email so we can help.',
        '',
        'Best,',
        'SHARE Bear Admin Team',
    ]
    body = '\n'.join(body_lines)
    return f'mailto:{quote(recipient)}?subject={quote(subject)}&body={quote(body)}'


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
        q.video_mime = 'video/mp4'
        if q.has_video and q.video_path:
            q.signed_video_url = create_signed_video_url(q.video_path, expires_in=1200)
            q.video_mime = video_mime_type_from_path(q.video_path)
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

    form = AdminAcceptQuoteForm(request.POST)
    if not form.is_valid():
        e = list(form.errors.values())[0][0] if form.errors else 'Invalid input.'
        messages.error(request, e)
        return redirect('admin_quotes')

    final = form.cleaned_data['final_offer']
    quote.quote_accepted_by_admin = True
    quote.quote_reviewed_at = timezone.now()
    update_fields = ['quote_accepted_by_admin', 'quote_reviewed_at']
    if final:
        quote.admin_confirmed_offer_display = final
        update_fields.append('admin_confirmed_offer_display')
    quote.save(update_fields=update_fields)
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
        q.approval_mailto_url = None
        q.signed_video_url = None
        q.video_mime = 'video/mp4'
        if q.has_video and q.video_path:
            q.signed_video_url = create_signed_video_url(q.video_path, expires_in=1200)
            q.video_mime = video_mime_type_from_path(q.video_path)
        if q.picked_up:
            picked_up_list.append(q)
        elif q.quote_accepted_by_admin:
            q.approval_mailto_url = build_approval_mailto_url(q)
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
    q = get_object_or_404(AIQuote, pk=quote_id)
    if not q.has_video:
        messages.error(
            request,
            f'Cannot approve "{q.item_name}" — the user has not uploaded a video yet.',
        )
        return redirect('admin_kanban')
    if q.quote_accepted_by_admin:
        messages.info(request, f'"{q.item_name}" is already approved.')
        return redirect('admin_kanban')
    form = AdminAcceptQuoteForm(request.POST)
    if not form.is_valid():
        e = list(form.errors.values())[0][0] if form.errors else 'Invalid input.'
        messages.error(request, e)
        return redirect('admin_kanban')
    final = form.cleaned_data['final_offer']
    q.quote_accepted_by_admin = True
    q.quote_reviewed_at = timezone.now()
    update_fields = ['quote_accepted_by_admin', 'quote_reviewed_at']
    if final:
        q.admin_confirmed_offer_display = final
        update_fields.append('admin_confirmed_offer_display')
    q.save(update_fields=update_fields)
    messages.success(request, f'Approved "{q.item_name}" for @{q.user.username}.')
    return redirect('admin_kanban')


@require_http_methods(['POST'])
def admin_kanban_pickup_view(request, quote_id: int):
    if not request.user.is_authenticated:
        return redirect(f"{settings.LOGIN_URL}?next={quote(request.path)}")
    if not (request.user.is_staff or request.user.is_superuser):
        return HttpResponseForbidden('You do not have access to this page.')
    q = get_object_or_404(AIQuote, pk=quote_id)
    if not q.quote_accepted_by_admin:
        messages.error(request, f'"{q.item_name}" must be approved before it can be marked as picked up.')
        return redirect('admin_kanban')
    if q.picked_up:
        messages.info(request, f'"{q.item_name}" is already marked as picked up.')
        return redirect('admin_kanban')
    q.picked_up = True
    q.picked_up_at = timezone.now()
    q.save(update_fields=['picked_up', 'picked_up_at'])
    messages.success(request, f'"{q.item_name}" for @{q.user.username} marked as picked up.')
    return redirect('admin_kanban')


@require_http_methods(['POST'])
def admin_kanban_unapprove_view(request, quote_id: int):
    if not request.user.is_authenticated:
        return redirect(f"{settings.LOGIN_URL}?next={quote(request.path)}")
    if not (request.user.is_staff or request.user.is_superuser):
        return HttpResponseForbidden('You do not have access to this page.')
    q = get_object_or_404(AIQuote, pk=quote_id)
    if not q.quote_accepted_by_admin:
        messages.info(request, f'"{q.item_name}" has not been approved yet.')
        return redirect('admin_kanban')
    if q.picked_up:
        messages.error(request, f'Revert "{q.item_name}" from Picked Up to Approved first.')
        return redirect('admin_kanban')
    q.quote_accepted_by_admin = False
    q.quote_reviewed_at = None
    q.save(update_fields=['quote_accepted_by_admin', 'quote_reviewed_at'])
    messages.success(request, f'Reverted "{q.item_name}" back to Awaiting.')
    return redirect('admin_kanban')


@require_http_methods(['POST'])
def admin_kanban_unpickup_view(request, quote_id: int):
    if not request.user.is_authenticated:
        return redirect(f"{settings.LOGIN_URL}?next={quote(request.path)}")
    if not (request.user.is_staff or request.user.is_superuser):
        return HttpResponseForbidden('You do not have access to this page.')
    q = get_object_or_404(AIQuote, pk=quote_id)
    if not q.picked_up:
        messages.info(request, f'"{q.item_name}" is not marked as picked up.')
        return redirect('admin_kanban')
    q.picked_up = False
    q.picked_up_at = None
    q.save(update_fields=['picked_up', 'picked_up_at'])
    messages.success(request, f'Reverted "{q.item_name}" back to Approved.')
    return redirect('admin_kanban')
