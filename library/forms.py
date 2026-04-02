from django import forms


class BookUploadForm(forms.Form):
    file = forms.FileField(widget=forms.FileInput(attrs={"accept": ".pdf,.epub"}))
    title = forms.CharField(max_length=255)
    author = forms.CharField(max_length=255)
