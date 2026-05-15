# Generated manually to match the current seed data shape.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accommodations', '0007_alter_accommodation_capacity_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='accommodation',
            name='hotline',
            field=models.CharField(blank=True, max_length=50),
        ),
        migrations.AlterField(
            model_name='accommodation',
            name='image_url',
            field=models.URLField(blank=True, max_length=500, null=True),
        ),
    ]
