import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("presupuestos", "0003_alter_categoriaproductotipogasto_tipo_gasto_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="Categoria",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("nombre", models.CharField(max_length=100, unique=True)),
            ],
            options={
                "verbose_name_plural": "categorias",
                "ordering": ["nombre"],
            },
        ),
        migrations.AddField(
            model_name="tipogasto",
            name="categoria",
            field=models.ForeignKey(
                default=1,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="tipos_gasto",
                to="presupuestos.categoria",
            ),
            preserve_default=False,
        ),
        migrations.AlterModelOptions(
            name="tipogasto",
            options={"ordering": ["categoria__nombre", "nombre"]},
        ),
    ]
