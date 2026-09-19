from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("conciliacion", "0005_movimientolibro_movimiento_libro_debe_no_negativo_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="cuentabancaria",
            name="banco",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                to="conciliacion.banco",
            ),
        ),
        migrations.AlterField(
            model_name="cuentabancaria",
            name="tipo_cuenta",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                to="conciliacion.tipocuenta",
            ),
        ),
        migrations.AlterField(
            model_name="cuentabancaria",
            name="moneda",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                to="conciliacion.moneda",
            ),
        ),
    ]
