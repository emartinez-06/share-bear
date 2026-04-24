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
