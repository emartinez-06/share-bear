from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from core.google_calendar import (
    create_pickup_event,
    is_pickup_calendar_configured,
    list_candidate_slots,
    parse_slot_post_key,
    resolve_available_preset_slot,
)
from core.models import AIQuote

from .forms import LoginForm, SignupForm


def signup_view(request):
    if request.user.is_authenticated:
        return redirect('home')
    if request.method == 'POST':
        form = SignupForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, f'Welcome to SHARE Bear, {user.first_name or user.username}!')
            return redirect('home')
    else:
        form = SignupForm()
    return render(request, 'users/signup.html', {'form': form})


def login_view(request):
    if request.user.is_authenticated:
        return redirect('home')
    if request.method == 'POST':
        form = LoginForm(request.POST)
        if form.is_valid():
            user = authenticate(
                request,
                username=form.cleaned_data['username'],
                password=form.cleaned_data['password'],
            )
            if user is not None:
                login(request, user)
                next_url = request.GET.get('next', 'home')
                return redirect(next_url)
            form.add_error(None, 'Invalid username or password.')
    else:
        form = LoginForm()
    return render(request, 'users/login.html', {'form': form})


def logout_view(request):
    logout(request)
    return redirect('home')


@login_required
def profile_view(request):
    quotes = list(AIQuote.objects.filter(user=request.user).order_by('-created_at')[:100])
    pickup_slots: list[dict] = []
    if is_pickup_calendar_configured():
        try:
            pickup_slots = list_candidate_slots()
        except Exception:
            messages.error(
                request,
                'Could not load pickup time slots. Check Calendar API configuration.',
            )
    eligible = [
        q
        for q in quotes
        if q.quote_accepted_by_admin
        and not q.picked_up
        and not (q.google_event_id or '').strip()
    ]
    return render(
        request,
        'users/profile.html',
        {
            'quotes': quotes,
            'pickup_slots': pickup_slots,
            'pickup_calendar_configured': is_pickup_calendar_configured(),
            'pickup_eligible_quotes': eligible,
            # Must match GOOGLE_PICKUP_TIMEZONE / Calendar insert so |date is not shown in UTC
            'pickup_display_timezone': (getattr(settings, 'GOOGLE_PICKUP_TIMEZONE', 'America/Chicago') or 'America/Chicago'),
        },
    )


@login_required
@require_http_methods(['POST'])
def profile_attach_pickup_view(request):
    if not is_pickup_calendar_configured():
        messages.error(request, 'Pickup scheduling is not configured.')
        return redirect('profile')

    slot_key = (request.POST.get('slot_key') or '').strip()
    parsed = parse_slot_post_key(slot_key)
    if not parsed:
        messages.error(
            request,
            'That time selection is invalid or has expired. Refresh the page and try again.',
        )
        return redirect('profile')
    calendar_id, start_guess, end_guess = parsed
    raw_ids = request.POST.getlist('quote_ids')
    quote_ids: list[int] = []
    for x in raw_ids:
        try:
            quote_ids.append(int(x))
        except (TypeError, ValueError):
            continue
    quote_ids = sorted(set(quote_ids))
    if not quote_ids:
        messages.error(request, 'Choose a time slot and at least one item.')
        return redirect('profile')

    quotes = list(
        AIQuote.objects.filter(user=request.user, pk__in=quote_ids).order_by('pk')
    )
    if len(quotes) != len(quote_ids):
        messages.error(
            request,
            'You can only schedule pickup for your own items.',
        )
        return redirect('profile')
    for q in quotes:
        if not (q.quote_accepted_by_admin and not q.picked_up):
            messages.error(
                request,
                'Only confirmed buy-backs that are not yet picked up can be scheduled.',
            )
            return redirect('profile')
        if (q.google_event_id or '').strip():
            messages.error(
                request,
                'An item in your selection already has a scheduled pickup. Contact support to change it.',
            )
            return redirect('profile')

    u = request.user
    user_label = (u.get_full_name() or '').strip() or f'@{u.username}'
    user_email = (u.email or '').strip()

    with transaction.atomic():
        resolved = resolve_available_preset_slot(calendar_id, start_guess, end_guess)
        if not resolved:
            messages.error(
                request,
                'That time slot is no longer available. Refresh the page and pick another.',
            )
            return redirect('profile')
        slot_start, slot_end = resolved

        claimed = create_pickup_event(
            calendar_id,
            slot_start,
            slot_end,
            user_email=user_email,
            user_label=user_label,
            quote_ids=quote_ids,
            item_names=[q.item_name for q in quotes],
        )
        if not claimed:
            messages.error(
                request,
                'Could not book that time slot. It may have just been taken. Try again.',
            )
            return redirect('profile')

        event_id = (claimed.get('id') or '').strip()
        link = (claimed.get('htmlLink') or '').strip()
        for q in quotes:
            q.google_calendar_id = calendar_id
            q.google_event_id = event_id
            q.pickup_event_html_link = link[:2000] if link else q.pickup_event_html_link
            # Store canonical preset times so availability matches _slot_taken_in_db
            q.pickup_starts_at = slot_start
            q.pickup_ends_at = slot_end
            q.save(
                update_fields=[
                    'google_calendar_id',
                    'google_event_id',
                    'pickup_event_html_link',
                    'pickup_starts_at',
                    'pickup_ends_at',
                ]
            )

    messages.success(
        request,
        f'Pickup scheduled for {len(quotes)} item(s). You can open the event in Google Calendar from the links below.',
    )
    return redirect('profile')
