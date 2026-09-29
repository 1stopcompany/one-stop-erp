from django import forms

from .models import Blueprint, BlueprintRevision


class BlueprintForm(forms.ModelForm):
    """A new drawing sheet together with its first revision file."""
    revision = forms.CharField(
        max_length=20, initial="0", widget=forms.TextInput(attrs={"class": "form-control"}),
        help_text="Revision being uploaded, e.g. 0, A, B",
    )
    file = forms.FileField(widget=forms.ClearableFileInput(attrs={"class": "form-control"}))
    notes = forms.CharField(required=False, max_length=255, widget=forms.TextInput(attrs={"class": "form-control"}))

    class Meta:
        model = Blueprint
        fields = ("drawing_number", "title", "discipline")
        widgets = {
            "drawing_number": forms.TextInput(attrs={"class": "form-control"}),
            "title": forms.TextInput(attrs={"class": "form-control"}),
            "discipline": forms.Select(attrs={"class": "form-select"}),
        }

    def __init__(self, *args, project=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.project = project
        # Same validator as the model field, so the file is checked before anything is saved.
        self.fields["file"].validators.extend(BlueprintRevision._meta.get_field("file").validators)

    def clean_drawing_number(self):
        number = self.cleaned_data["drawing_number"].strip()
        if self.project and Blueprint.objects.filter(project=self.project, drawing_number__iexact=number).exists():
            raise forms.ValidationError(
                f"Drawing {number} already exists in this project -- open it and upload a new revision instead."
            )
        return number


class RevisionForm(forms.ModelForm):
    class Meta:
        model = BlueprintRevision
        fields = ("revision", "file", "notes")
        widgets = {
            "revision": forms.TextInput(attrs={"class": "form-control"}),
            "file": forms.ClearableFileInput(attrs={"class": "form-control"}),
            "notes": forms.TextInput(attrs={"class": "form-control"}),
        }

    def __init__(self, *args, blueprint=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.blueprint = blueprint

    def clean_revision(self):
        revision = self.cleaned_data["revision"].strip()
        if self.blueprint and self.blueprint.revisions.filter(revision__iexact=revision).exists():
            raise forms.ValidationError(f"Revision {revision} of this drawing was already uploaded.")
        return revision
