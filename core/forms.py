import re
from decimal import Decimal, InvalidOperation

from django import forms
from django.conf import settings


class AIQuoteForm(forms.Form):
    item_name = forms.CharField(
        label="Item name",
        max_length=200,
        widget=forms.TextInput(
            attrs={
                "class": "field-input",
                "placeholder": "e.g. MacBook Pro 14",
            }
        ),
    )
    description = forms.CharField(
        label="Description",
        widget=forms.Textarea(
            attrs={
                "class": "field-input min-h-[120px] resize-y",
                "rows": 4,
                "placeholder": "Condition, year, key specs, accessories…",
            }
        ),
    )
    make = forms.CharField(
        label="Make / brand",
        max_length=120,
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "field-input",
                "placeholder": "e.g. Apple, Dell",
            }
        ),
    )
    model = forms.CharField(
        label="Model",
        max_length=120,
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "field-input",
                "placeholder": "e.g. M3 Pro, XPS 13",
            }
        ),
    )
    unknown_make_model = forms.BooleanField(
        label="Unknown make and model (generic quote)",
        required=False,
        widget=forms.CheckboxInput(
            attrs={
                "class": "rounded border-outline-variant text-primary focus:ring-primary",
            }
        ),
    )

    def clean(self):
        cleaned = super().clean()
        unknown = cleaned.get("unknown_make_model")
        make = (cleaned.get("make") or "").strip()
        model = (cleaned.get("model") or "").strip()
        if not unknown and (not make or not model):
            raise forms.ValidationError(
                "Enter both make and model, or check “Unknown make and model” for a generic quote."
            )
        item_name = (cleaned.get("item_name") or "").strip()
        description = (cleaned.get("description") or "").strip()
        if _looks_like_gibberish(item_name, description):
            raise forms.ValidationError(
                "Please enter a real item name and a clearer description."
            )
        return cleaned


def _looks_like_gibberish(item_name: str, description: str) -> bool:
    text = f"{item_name} {description}".strip().lower()
    if re.search(r"(asdf|qwer|zxcv|hjkl|poiuy|lkjh|mnbv)", text):
        return True
    words = re.findall(r"[a-z]{2,}", text)
    if len(words) < 3:
        return True

    alpha_chars = sum(1 for c in text if c.isalpha())
    if alpha_chars < 10:
        return True

    vowel_words = sum(1 for w in words if re.search(r"[aeiouy]", w))
    if (vowel_words / len(words)) < 0.35:
        return True

    return False


_VIDEO_TYPES = {
    'video/mp4',
    'video/webm',
    'video/quicktime',
    'video/mov',
    'application/octet-stream',  # some browsers send for .mov
}


class QuoteVideoForm(forms.Form):
    video = forms.FileField(
        label='Condition video',
        help_text='MP4, WebM, or MOV. Max size shown below.',
    )

    def __init__(self, *args, max_bytes: int | None = None, **kwargs):
        self.max_bytes = max_bytes or getattr(
            settings, 'QUOTE_VIDEO_MAX_BYTES', 100 * 1024 * 1024
        )
        super().__init__(*args, **kwargs)

    def clean_video(self):
        f = self.cleaned_data.get('video')
        if f is None:
            raise forms.ValidationError('Select a video file.')
        if f.size > self.max_bytes:
            mb = self.max_bytes // (1024 * 1024)
            raise forms.ValidationError(f'File is too large (max {mb} MB).')
        ct = (getattr(f, 'content_type', None) or '').lower()
        name = (getattr(f, 'name', '') or '').lower()
        if ct not in _VIDEO_TYPES and not any(
            name.endswith(ext) for ext in ('.mp4', '.webm', '.mov', '.m4v')
        ):
            raise forms.ValidationError('Please upload a video (MP4, WebM, or MOV).')
        return f


def normalize_confirmed_buyback_offer(value: str) -> str | None:
    """
    Parse optional staff-entered buy-back amount. Returns None to keep the AI offer.
    Raises ValidationError for invalid input.
    """
    s = (value or '').strip()
    if not s:
        return None
    clean = s.replace(',', '').lstrip('$').strip()
    if not clean:
        return None
    try:
        d = Decimal(clean)
    except InvalidOperation as e:
        raise forms.ValidationError('Enter a valid amount (e.g. 150 or $150.00).') from e
    if d < 0 or d > Decimal('999999.99'):
        raise forms.ValidationError('Amount out of range.')
    q = d.quantize(Decimal('0.01'))
    if q == q.to_integral_value():
        return f'${int(q):,}'
    return f'${q:,.2f}'


class AdminAcceptQuoteForm(forms.Form):
    final_offer = forms.CharField(
        required=False,
        label='',
        widget=forms.TextInput(
            attrs={
                'class': 'field-input',
                'placeholder': 'e.g. 150 (leave blank for AI offer)',
                'autocomplete': 'off',
            },
        ),
    )

    def clean_final_offer(self):
        return normalize_confirmed_buyback_offer(self.cleaned_data.get('final_offer', ''))


class BookingLinkForm(forms.Form):
    booking_link = forms.URLField(
        label='Microsoft Booking link',
        max_length=1024,
        required=False,
        widget=forms.URLInput(attrs={
            'class': 'field-input',
            'placeholder': 'https://outlook.office365.com/book/...',
        }),
    )
