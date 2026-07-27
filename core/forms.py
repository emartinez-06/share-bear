from decimal import Decimal, InvalidOperation

from django import forms
from django.conf import settings

from .models import Listing


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
        return cleaned


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


_IMAGE_TYPES = {'image/jpeg', 'image/png', 'image/webp'}
_IMAGE_EXTENSIONS = ('.jpg', '.jpeg', '.png', '.webp')


def listing_image_upload_error(f, max_bytes: int | None = None) -> str | None:
    """
    Validate one uploaded image file. Returns an error message (naming the
    file) if invalid, or None if it's fine. Used for both a single-file
    form and a multi-file upload loop, since Django's FileField doesn't
    natively support multiple files without a custom field.
    """
    max_bytes = max_bytes or getattr(settings, 'LISTING_IMAGE_MAX_BYTES', 10 * 1024 * 1024)
    name = (getattr(f, 'name', '') or 'file').strip()
    if f.size > max_bytes:
        mb = max_bytes // (1024 * 1024)
        return f'{name}: too large (max {mb} MB).'
    ct = (getattr(f, 'content_type', None) or '').lower()
    if ct not in _IMAGE_TYPES and not any(name.lower().endswith(ext) for ext in _IMAGE_EXTENSIONS):
        return f'{name}: must be a JPEG, PNG, or WebP image.'
    return None


class ListingForm(forms.Form):
    title = forms.CharField(max_length=200)
    description = forms.CharField(widget=forms.Textarea)
    category = forms.CharField(max_length=100, required=False)
    condition = forms.ChoiceField(
        choices=[('', '—')] + Listing.Condition.choices, required=False)
    price = forms.DecimalField(max_digits=8, decimal_places=2, min_value=Decimal('0'))
    msrp = forms.DecimalField(
        max_digits=8, decimal_places=2, min_value=Decimal('0'), required=False,
        label='Original retail price (MSRP)',
    )
    msrp_url = forms.URLField(max_length=1024, required=False, label='Original item link')
    quantity = forms.IntegerField(min_value=1, initial=1)
    status = forms.ChoiceField(choices=Listing.Status.choices)
