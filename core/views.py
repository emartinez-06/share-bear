import logging
from urllib.parse import quote

from django.conf import settings
from django.http import HttpResponseForbidden
from django.shortcuts import redirect, render

from .forms import AIQuoteForm
from .gemini_quote import build_quote_prompt, get_quote_from_gemini
from .models import AIQuote

logger = logging.getLogger(__name__)


def home_view(request):
    return render(
        request,
        'index.html',
        {'vercel_analytics_enabled': settings.VERCEL_ANALYTICS_ENABLED},
    )


def admin_quotes_view(request):
    if not request.user.is_authenticated:
        return redirect(f"{settings.LOGIN_URL}?next={quote(request.path)}")
    if not (request.user.is_staff or request.user.is_superuser):
        return HttpResponseForbidden('You do not have access to this page.')

    quotes = AIQuote.objects.select_related('user').all()
    return render(
        request,
        'admin_quotes.html',
        {
            'quotes': quotes,
            'vercel_analytics_enabled': settings.VERCEL_ANALYTICS_ENABLED,
        },
    )


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
                        'gemini_error': str(e) or 'Could not get a quote right now. Try again later.',
                    },
                )
            if request.user.is_authenticated:
                AIQuote.objects.create(
                    user=request.user,
                    item_name=data['item_name'],
                    description=data['description'],
                    make=make,
                    model=model,
                    unknown_make_model=bool(data.get('unknown_make_model')),
                    quote_text=quote_text,
                )
            return render(
                request,
                'ai_quote_success.html',
                {
                    'quote_text': quote_text,
                    'item_name': data['item_name'],
                    'vercel_analytics_enabled': settings.VERCEL_ANALYTICS_ENABLED,
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
        },
    )
