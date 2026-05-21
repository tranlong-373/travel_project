from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("chat_api", "0001_place_reference"),
    ]

    operations = [
        migrations.AddField(
            model_name="placereference",
            name="query_text",
            field=models.CharField(blank=True, max_length=300),
        ),
        migrations.AddField(
            model_name="placereference",
            name="normalized_query",
            field=models.CharField(blank=True, db_index=True, max_length=300),
        ),
        migrations.AddField(
            model_name="placereference",
            name="district",
            field=models.CharField(blank=True, max_length=120),
        ),
        migrations.AddField(
            model_name="placereference",
            name="city",
            field=models.CharField(blank=True, max_length=120),
        ),
        migrations.AddField(
            model_name="placereference",
            name="country",
            field=models.CharField(blank=True, max_length=120),
        ),
        migrations.AddField(
            model_name="placereference",
            name="last_used_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
