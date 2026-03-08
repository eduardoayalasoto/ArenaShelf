from django import forms


class BookUploadForm(forms.Form):
    file = forms.FileField()
    title = forms.CharField(max_length=255)
    author = forms.CharField(max_length=255)
