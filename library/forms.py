from django import forms


class BookUploadForm(forms.Form):
    file = forms.FileField(widget=forms.FileInput(attrs={
        "accept": ".pdf,.epub",
        "class": (
            "w-full text-sm text-slate-600 cursor-pointer rounded-xl border border-slate-200 bg-white "
            "file:mr-4 file:py-2.5 file:px-4 file:rounded-l-xl file:border-0 "
            "file:text-sm file:font-semibold file:bg-brand-navy file:text-white "
            "hover:file:bg-brand-dark file:cursor-pointer file:transition-colors"
        ),
    }))
