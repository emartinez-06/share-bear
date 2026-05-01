import logging
from urllib.parse import quote, urlencode

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponseForbidden, HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from .forms import AdminAcceptQuoteForm, AIQuoteForm, BookingLinkForm, QuoteVideoForm
from .gemini_quote import build_quote_prompt, format_offers_total, format_share_bear_offer_display, get_quote_from_gemini
from .models import AIQuote
from .supabase_storage import create_signed_video_url, is_storage_configured, upload_quote_video
from .video_utils import file_extension_for_upload, video_mime_type_from_path

logger = logging.getLogger(__name__)

# Shown on /ai-quote/dev-success/ when DEBUG is True (no Gemini call).
DEV_MOCK_QUOTE_ITEM_NAME = 'Sample item (dev preview)'
DEV_MOCK_OFFER_DISPLAY = '$127'
LEGACY_ASSIGNED_ADMIN_PLACEHOLDER = 'Erick'


def _normalized_admin_name(raw_name: str) -> str:
    return (raw_name or '').strip()


def _effective_assigned_admin_name(quote_obj: AIQuote) -> str:
    assigned = _normalized_admin_name(quote_obj.assigned_admin_name)
    if assigned:
        return assigned
    if quote_obj.quote_accepted_by_admin:
        return LEGACY_ASSIGNED_ADMIN_PLACEHOLDER
    return ''


def build_approval_mailto_url(quote_obj: AIQuote) -> str | None:
    recipient = (quote_obj.user.email or '').strip()
    if not recipient:
        return None

    admin_name = _effective_assigned_admin_name(quote_obj)
    if not admin_name:
        return None
    subject = f'Your SHARE Bear item has been approved: {quote_obj.item_name}'
    if admin_name:
        subject += f' — {admin_name}'
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


def build_video_reminder_mailto_url(quote_obj: AIQuote) -> str | None:
    """mailto link reminding the user to upload a video for their awaiting item."""
    recipient = (quote_obj.user.email or '').strip()
    if not recipient:
        return None

    admin_name = _normalized_admin_name(quote_obj.assigned_admin_name)
    if not admin_name:
        return None
    subject = f'Action needed: upload a video for your SHARE Bear item — {quote_obj.item_name}'
    if admin_name:
        subject += f' | {admin_name}'
    body_lines = [
        f'Hi {quote_obj.user.first_name or quote_obj.user.username},',
        '',
        f'Your item "{
            quote_obj.item_name}" is awaiting review, but we still need a short video',
        "showing the item's current condition before we can process your buy-back offer.",
        '',
        'Please log in to your SHARE Bear account and upload a video from your item page:',
        '  https://sharebear.app',
        '',
        'The video only needs to be a few seconds long — just show us the item clearly.',
        '',
        'If you have any questions, reply directly to this email.',
        '',
        'Thanks,',
        'SHARE Bear Admin Team',
    ]
    body = '\n'.join(body_lines)
    return f'mailto:{quote(recipient)}?subject={quote(subject)}&body={quote(body)}'


def build_group_location_mailto_url(user, booked_items: list, admin_name: str = '') -> str | None:
    """Single location-request email covering all booked items for a user's approved group."""
    recipient = (user.email or '').strip()
    if not recipient or not booked_items:
        return None

    admin_name = admin_name.strip()
    if not admin_name:
        return None
    subject = 'Pickup location needed for your SHARE Bear item(s)'
    if admin_name:
        subject += f' — {admin_name}'
    item_lines = '\n'.join(f'- {q.item_name}' for q in booked_items)
    body_lines = [
        f'Hi {user.first_name or user.username},',
        '',
        'Confirmed! You have a pickup scheduled for these item(s):',
        item_lines,
        '',
        'Time: [ADMIN CHECK BOOKING TIME]',
        '',
        'Please reply to this email with where you would like to meet:',
        '- Residential Hall',
        '- Draper Parking Lot (Lot 25) next to Traditions Plaza',
        '- Off-campus apartment (include apartment number & Address)',
        '',
        'Note: A $15 pickup fee applies if we come to you.',
        'No fee if you drop off at the parking lot next to Traditions Plaza / Draper BU Lot 25.',
        '',
        'Thanks,',
        'SHARE Bear Admin Team',
    ]
    body = '\n'.join(body_lines)
    return f'mailto:{quote(recipient)}?subject={quote(subject)}&body={quote(body)}'


def build_pickup_location_mailto_url(quote_obj: AIQuote) -> str | None:
    recipient = (quote_obj.user.email or '').strip()
    if not recipient:
        return None
    if not ((quote_obj.google_event_id or '').strip() or quote_obj.booking_initiated):
        return None

    admin_name = _effective_assigned_admin_name(quote_obj)
    if not admin_name:
        return None

    pickup_time = 'your scheduled pickup slot'
    if quote_obj.pickup_starts_at:
        start_local = timezone.localtime(quote_obj.pickup_starts_at)
        if quote_obj.pickup_ends_at:
            end_local = timezone.localtime(quote_obj.pickup_ends_at)
            pickup_time = f'{
                start_local:%A, %b %-d at %-I:%M %p} to {end_local:%-I:%M %p}'
        else:
            pickup_time = f'{start_local:%A, %b %-d at %-I:%M %p}'

    subject = f'Pickup location confirmation needed: {quote_obj.item_name}'
    if admin_name:
        subject += f' — {admin_name}'
    body_lines = [
        f'Hi {quote_obj.user.first_name or quote_obj.user.username},',
        '',
        'Confirmed! You booked a pickup slot for these item(s):',
        f'- {quote_obj.item_name}',
        '',
        f'Time: {pickup_time}',
        '',
        'Please reply to this email with where you would like to meet:',
        '- Penland',
        '- Martin',
        '- Collins',
        '- Off-campus apartment (include apartment number)',
        '',
        'Thanks,',
        'SHARE Bear Admin Team',
    ]
    body = '\n'.join(body_lines)
    return f'mailto:{quote(recipient)}?subject={quote(subject)}&body={quote(body)}'


def build_group_approval_mailto_url(user, approved_items: list, admin_name: str = '') -> str | None:
    recipient = (user.email or '').strip()
    admin_name = admin_name.strip()
    if not recipient or not approved_items or not admin_name:
        return None

    subject = f'Your SHARE Bear items are approved — complete booking — {admin_name}'
    item_lines = '\n'.join(f'- {q.item_name}: {q.offer_display}' for q in approved_items)
    body_lines = [
        f'Hi {user.first_name or user.username},',
        '',
        'Great news — all your submitted SHARE Bear items are approved:',
        item_lines,
        '',
        'Please fill out the booking link under your account profile to schedule pickup.',
        '',
        'If anything looks off, reply directly to this email.',
        '',
        'Best,',
        'SHARE Bear Admin Team',
    ]
    body = '\n'.join(body_lines)
    return f'mailto:{quote(recipient)}?subject={quote(subject)}&body={quote(body)}'


def build_group_video_reminder_mailto_url(user, awaiting_items: list, admin_name: str = '') -> str | None:
    recipient = (user.email or '').strip()
    admin_name = admin_name.strip()
    if not recipient or not awaiting_items or not admin_name:
        return None

    missing_video = [q for q in awaiting_items if not q.has_video]
    if not missing_video:
        return None

    subject = f'Action needed: upload video(s) for your SHARE Bear items — {admin_name}'
    item_lines = '\n'.join(f'- {q.item_name}' for q in missing_video)
    body_lines = [
        f'Hi {user.first_name or user.username},',
        '',
        'Before we can review your items, we still need short videos for:',
        item_lines,
        '',
        'Please log in to your SHARE Bear account and upload videos from your item page:',
        '  https://sharebear.app',
        '',
        'If you have questions, reply to this email.',
        '',
        'Thanks,',
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
        AIQuote.objects.select_related(
            'user').all().order_by('-created_at')[:200]
    )
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
        e = list(form.errors.values())[
            0][0] if form.errors else 'Invalid input.'
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
        f'You accepted the buy-back offer for @{
            quote.user.username} — {quote.item_name}.',
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
                success_url = reverse(
                    'ai_quote_success_detail', kwargs={'quote_id': q.pk})
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
        messages.info(
            request, 'This offer is already confirmed by SHARE Bear.')
        return redirect('ai_quote_success_detail', quote_id=quote.pk)

    form = QuoteVideoForm(
        request.POST,
        request.FILES,
        max_bytes=settings.QUOTE_VIDEO_MAX_BYTES,
    )
    if not form.is_valid():
        err = form.errors.get('video') or form.errors.get(
            '__all__', ['Invalid upload.'])
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
        messages.error(request, str(
            e) or 'Upload failed. Try a smaller file or a different format.')
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

    all_quotes = list(AIQuote.objects.select_related(
        'user').order_by('-created_at'))
    legacy_approved_missing_admin_ids = [
        q.pk for q in all_quotes
        if q.quote_accepted_by_admin and not _normalized_admin_name(q.assigned_admin_name)
    ]
    if legacy_approved_missing_admin_ids:
        AIQuote.objects.filter(pk__in=legacy_approved_missing_admin_ids).update(
            assigned_admin_name=LEGACY_ASSIGNED_ADMIN_PLACEHOLDER
        )
        legacy_ids = set(legacy_approved_missing_admin_ids)
        for q in all_quotes:
            if q.pk in legacy_ids:
                q.assigned_admin_name = LEGACY_ASSIGNED_ADMIN_PLACEHOLDER

    user_stage_counts: dict[int, dict[str, int]] = {}
    for q in all_quotes:
        counts = user_stage_counts.setdefault(
            q.user_id, {'awaiting': 0, 'approved': 0, 'picked_up': 0, 'denied': 0}
        )
        if q.picked_up:
            counts['picked_up'] += 1
        elif q.quote_accepted_by_admin:
            counts['approved'] += 1
        elif q.denied:
            counts['denied'] += 1
        else:
            counts['awaiting'] += 1

    awaiting, approved, picked_up_list, denied_list = [], [], [], []
    for q in all_quotes:
        q.approval_mailto_url = None
        q.pickup_location_mailto_url = None
        q.video_reminder_mailto_url = None
        if q.picked_up:
            picked_up_list.append(q)
        elif q.quote_accepted_by_admin:
            q.approval_mailto_url = build_approval_mailto_url(q)
            q.pickup_location_mailto_url = build_pickup_location_mailto_url(q)
            approved.append(q)
        elif q.denied:
            denied_list.append(q)
        else:
            if not q.has_video:
                q.video_reminder_mailto_url = build_video_reminder_mailto_url(
                    q)
            awaiting.append(q)

    def _group_by_user(items: list) -> list[dict]:
        groups: dict[int, dict] = {}
        for q in items:
            uid = q.user_id
            if uid not in groups:
                groups[uid] = {'user': q.user, 'items': [],
                               'item_count': 0, 'admins': set()}
            groups[uid]['items'].append(q)
            groups[uid]['item_count'] += 1
            if q.assigned_admin_name:
                groups[uid]['admins'].add(q.assigned_admin_name)
        result = []
        for g in groups.values():
            admins_sorted = sorted(g['admins'])
            total = format_offers_total([q.offer_display for q in g['items']])
            assigned_admin = admins_sorted[0] if admins_sorted else ''
            result.append({
                **g,
                'admins': admins_sorted,
                'total_display': total,
                'assigned_admin': assigned_admin,
            })
        return result

    awaiting_by_user = _group_by_user(awaiting)
    for group in awaiting_by_user:
        counts = user_stage_counts.get(group['user'].pk, {})
        no_approved_items = counts.get('approved', 0) == 0
        group['video_update_mailto_url'] = build_group_video_reminder_mailto_url(
            group['user'],
            group['items'],
            admin_name=group['assigned_admin'],
        ) if no_approved_items else None

    approved_by_user = _group_by_user(approved)
    for group in approved_by_user:
        counts = user_stage_counts.get(group['user'].pk, {})
        group['all_items_approved'] = (
            counts.get('approved', 0) > 0
            and counts.get('awaiting', 0) == 0
            and counts.get('denied', 0) == 0
            and counts.get('picked_up', 0) == 0
        )
        group['approval_mailto_url'] = build_group_approval_mailto_url(
            group['user'],
            group['items'],
            admin_name=group['assigned_admin'],
        ) if group['all_items_approved'] else None
        booked = [q for q in group['items'] if q.booking_initiated or (q.google_event_id or '').strip()]
        group['location_mailto_url'] = build_group_location_mailto_url(
            group['user'], booked, admin_name=group['assigned_admin']
        )

    return render(
        request,
        'admin_kanban.html',
        {
            'awaiting': awaiting,
            'awaiting_by_user': awaiting_by_user,
            'approved': approved,
            'approved_by_user': approved_by_user,
            'picked_up': picked_up_list,
            'picked_up_by_user': _group_by_user(picked_up_list),
            'denied': denied_list,
            'denied_by_user': _group_by_user(denied_list),
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
            f'Cannot approve "{
                q.item_name}" — the user has not uploaded a video yet.',
        )
        return redirect('admin_kanban')
    if q.quote_accepted_by_admin:
        messages.info(request, f'"{q.item_name}" is already approved.')
        return redirect('admin_kanban')
    if not (q.assigned_admin_name or '').strip():
        messages.error(request, f'Take over this case first — no admin is assigned to "{q.item_name}".')
        return redirect('admin_kanban')
    form = AdminAcceptQuoteForm(request.POST)
    if not form.is_valid():
        e = list(form.errors.values())[
            0][0] if form.errors else 'Invalid input.'
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
    messages.success(request, f'Approved "{
                     q.item_name}" for @{q.user.username}.')
    return redirect('admin_kanban')


@require_http_methods(['POST'])
def admin_kanban_pickup_view(request, quote_id: int):
    if not request.user.is_authenticated:
        return redirect(f"{settings.LOGIN_URL}?next={quote(request.path)}")
    if not (request.user.is_staff or request.user.is_superuser):
        return HttpResponseForbidden('You do not have access to this page.')
    q = get_object_or_404(AIQuote, pk=quote_id)
    if not q.quote_accepted_by_admin:
        messages.error(request, f'"{
                       q.item_name}" must be approved before it can be marked as picked up.')
        return redirect('admin_kanban')
    if q.picked_up:
        messages.info(
            request, f'"{q.item_name}" is already marked as picked up.')
        return redirect('admin_kanban')
    q.picked_up = True
    q.picked_up_at = timezone.now()
    q.save(update_fields=['picked_up', 'picked_up_at'])
    messages.success(
        request, f'"{q.item_name}" for @{q.user.username} marked as picked up.')
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
        messages.error(request, f'Revert "{
                       q.item_name}" from Picked Up to Approved first.')
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


@require_http_methods(['GET'])
def admin_video_url_view(request, quote_id: int):
    """Return a fresh signed video URL as JSON; called lazily by JS so page load stays fast."""
    if not request.user.is_authenticated:
        return redirect(f"{settings.LOGIN_URL}?next={quote(request.path)}")
    if not (request.user.is_staff or request.user.is_superuser):
        return HttpResponseForbidden('You do not have access to this page.')
    q = get_object_or_404(AIQuote, pk=quote_id)
    if not q.has_video or not q.video_path:
        raise Http404('No video for this quote.')
    url = create_signed_video_url(q.video_path, expires_in=600)
    return JsonResponse({'url': url or '', 'mime': video_mime_type_from_path(q.video_path)})


@login_required
@require_http_methods(['POST'])
def booking_initiate_view(request):
    raw_ids = request.POST.getlist('quote_ids')
    quote_ids: list[int] = []
    for x in raw_ids:
        try:
            quote_ids.append(int(x))
        except (TypeError, ValueError):
            continue
    quote_ids = sorted(set(quote_ids))

    if not quote_ids:
        messages.error(
            request, 'Select at least one item before opening Google Booking.')
        return redirect('user_items')

    qs = list(AIQuote.objects.filter(pk__in=quote_ids, user=request.user))
    if len(qs) != len(quote_ids):
        messages.error(
            request, 'One or more selected items could not be found.')
        return redirect('user_items')

    for q in qs:
        if not (q.quote_accepted_by_admin and not q.picked_up):
            messages.error(
                request, f'"{q.item_name}" is not eligible for booking.')
            return redirect('user_items')
        if q.booking_initiated or (q.google_event_id or '').strip():
            messages.error(
                request, f'"{q.item_name}" already has a booking in progress.')
            return redirect('user_items')

    AIQuote.objects.filter(pk__in=quote_ids, user=request.user).update(
        booking_initiated=True)

    u = request.user
    name = (u.get_full_name() or u.username).strip()
    email = (u.email or '').strip()
    item_summary = '; '.join(f'#{q.pk} {q.item_name}' for q in qs)

    base_url = (getattr(settings, 'GOOGLE_BOOKING_URL', '') or '').strip()
    if base_url:
        separator = '&' if '?' in base_url else '?'
        params = urlencode(
            {'name': name, 'email': email, 'details': item_summary})
        booking_url = f'{base_url}{separator}{params}'
    else:
        messages.error(
            request, 'Booking URL is not configured. Contact SHARE Bear.')
        return redirect('user_items')

    return HttpResponseRedirect(booking_url)


@require_http_methods(['POST'])
def admin_kanban_reset_booking_view(request, quote_id: int):
    if not request.user.is_authenticated:
        return redirect(f"{settings.LOGIN_URL}?next={quote(request.path)}")
    if not (request.user.is_staff or request.user.is_superuser):
        return HttpResponseForbidden('You do not have access to this page.')
    q = get_object_or_404(AIQuote, pk=quote_id)
    if not q.booking_initiated:
        messages.info(
            request, f'"{q.item_name}" does not have a pending booking to reset.')
        return redirect('admin_kanban')
    q.booking_initiated = False
    q.save(update_fields=['booking_initiated'])
    messages.success(request, f'Booking reset for "{
                     q.item_name}" — item is bookable again.')
    return redirect('admin_kanban')


@require_http_methods(['POST'])
def admin_kanban_assign_admin_view(request, quote_id: int):
    if not request.user.is_authenticated:
        return redirect(f"{settings.LOGIN_URL}?next={quote(request.path)}")
    if not (request.user.is_staff or request.user.is_superuser):
        return HttpResponseForbidden('You do not have access to this page.')
    q = get_object_or_404(AIQuote, pk=quote_id)
    if not q.quote_accepted_by_admin or q.picked_up:
        messages.error(
            request, f'"{q.item_name}" must be in Approved to set an assigned admin.')
        return redirect('admin_kanban')
    assigned = (request.POST.get('assigned_admin_name') or '').strip()[:120]
    q.assigned_admin_name = assigned
    q.save(update_fields=['assigned_admin_name'])
    if assigned:
        messages.success(request, f'Assigned admin for "{
                         q.item_name}" set to {assigned}.')
    else:
        messages.success(
            request, f'Assigned admin cleared for "{q.item_name}".')
    return redirect('admin_kanban')


@require_http_methods(['POST'])
def admin_kanban_pickup_label_view(request, quote_id: int):
    if not request.user.is_authenticated:
        return redirect(f"{settings.LOGIN_URL}?next={quote(request.path)}")
    if not (request.user.is_staff or request.user.is_superuser):
        return HttpResponseForbidden('You do not have access to this page.')
    q = get_object_or_404(AIQuote, pk=quote_id)
    if not q.picked_up:
        messages.error(
            request, f'"{q.item_name}" must be in Picked Up to set color/number.')
        return redirect('admin_kanban')

    allowed_colors = {'red', 'blue', 'green',
                      'yellow', 'purple', 'orange', 'black', 'white'}
    color = (request.POST.get('pickup_label_color') or '').strip().lower()
    if color and color not in allowed_colors:
        messages.error(request, 'Choose a valid color.')
        return redirect('admin_kanban')

    number_raw = (request.POST.get('pickup_label_number') or '').strip()
    number: int | None = None
    if number_raw:
        try:
            number = int(number_raw)
        except ValueError:
            messages.error(request, 'Tag number must be a whole number.')
            return redirect('admin_kanban')
        if number <= 0:
            messages.error(request, 'Tag number must be greater than 0.')
            return redirect('admin_kanban')

    q.pickup_label_color = color
    q.pickup_label_number = number
    q.save(update_fields=['pickup_label_color', 'pickup_label_number'])
    messages.success(request, f'Updated pickup label for "{q.item_name}".')
    return redirect('admin_kanban')


@require_http_methods(['POST'])
def admin_kanban_deny_view(request, quote_id: int):
    if not request.user.is_authenticated:
        return redirect(f"{settings.LOGIN_URL}?next={quote(request.path)}")
    if not (request.user.is_staff or request.user.is_superuser):
        return HttpResponseForbidden('You do not have access to this page.')
    q = get_object_or_404(AIQuote, pk=quote_id)
    if q.quote_accepted_by_admin or q.picked_up:
        messages.error(request, f'Cannot deny "{
                       q.item_name}" — it is already approved or picked up.')
        return redirect('admin_kanban')
    reason = (request.POST.get('denial_reason') or '').strip()
    q.denied = True
    q.denial_reason = reason
    q.save(update_fields=['denied', 'denial_reason'])
    messages.success(request, f'Denied "{
                     q.item_name}" for @{q.user.username}.')
    return redirect('admin_kanban')


@require_http_methods(['POST'])
def admin_kanban_undeny_view(request, quote_id: int):
    if not request.user.is_authenticated:
        return redirect(f"{settings.LOGIN_URL}?next={quote(request.path)}")
    if not (request.user.is_staff or request.user.is_superuser):
        return HttpResponseForbidden('You do not have access to this page.')
    q = get_object_or_404(AIQuote, pk=quote_id)
    if not q.denied:
        messages.info(request, f'"{q.item_name}" has not been denied.')
        return redirect('admin_kanban')
    q.denied = False
    q.denial_reason = ''
    q.save(update_fields=['denied', 'denial_reason'])
    messages.success(request, f'Denial reversed for "{q.item_name}" — moved back to Awaiting.')
    return redirect('admin_kanban')


@require_http_methods(['POST'])
def admin_kanban_take_over_view(request, user_id: int):
    if not request.user.is_authenticated:
        return redirect(f"{settings.LOGIN_URL}?next={quote(request.path)}")
    if not (request.user.is_staff or request.user.is_superuser):
        return HttpResponseForbidden('You do not have access to this page.')
    User = get_user_model()
    target_user = get_object_or_404(User, pk=user_id)
    admin_name = (request.POST.get('admin_name') or '').strip()[:120]
    if not admin_name:
        messages.error(request, 'Enter an admin name to take over this case.')
        return redirect('admin_kanban')
    updated = AIQuote.objects.filter(
        user=target_user,
        denied=False,
        picked_up=False,
    ).update(assigned_admin_name=admin_name)
    messages.success(request, f'@{target_user.username} case taken over by {admin_name} ({updated} item(s) updated).')
    return redirect('admin_kanban')
