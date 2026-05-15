from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('preferences', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='userpreference',
            name='preferred_type',
            field=models.CharField(blank=True, choices=[('hotel', 'Hotel'), ('homestay', 'Homestay'), ('hostel', 'Hostel'), ('apartment', 'Apartment')], max_length=20, null=True),
        ),
    ]
