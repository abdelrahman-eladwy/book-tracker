from django import forms

from .db import STATUSES

STATUS_CHOICES = [(status, status) for status in STATUSES]


class BookForm(forms.Form):
    title = forms.CharField(max_length=200)
    author = forms.CharField(max_length=200)
    category = forms.CharField(max_length=100)
    status = forms.ChoiceField(choices=STATUS_CHOICES)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Add Bootstrap classes to every widget.
        for name, field in self.fields.items():
            css = "form-select" if name == "status" else "form-control"
            field.widget.attrs["class"] = css


class StatusForm(forms.Form):
    status = forms.ChoiceField(choices=STATUS_CHOICES)
