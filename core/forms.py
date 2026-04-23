from django import forms


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
