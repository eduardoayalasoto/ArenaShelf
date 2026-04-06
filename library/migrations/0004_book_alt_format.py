from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("library", "0003_add_google_books_metadata"),
    ]

    operations = [
        migrations.AddField(
            model_name="book",
            name="alt_blob",
            field=models.BinaryField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="book",
            name="alt_extension",
            field=models.CharField(blank=True, max_length=16),
        ),
    ]
