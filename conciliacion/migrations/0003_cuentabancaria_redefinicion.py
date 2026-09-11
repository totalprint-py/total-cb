# Redefinición del catálogo ``CuentaBancaria`` (generada manualmente).
#
# Renombra ``numero`` -> ``numero_cuenta`` y ``nombre`` -> ``denominacion``
# (preservando datos), cambia las claves foráneas de ``PROTECT`` a ``CASCADE``
# y agrega el campo ``saldo_inicial``.

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('conciliacion', '0002_alter_banco_codigo_alter_conceptoajuste_codigo_and_more'),
    ]

    operations = [
        migrations.RenameField(
            model_name='cuentabancaria',
            old_name='numero',
            new_name='numero_cuenta',
        ),
        migrations.RenameField(
            model_name='cuentabancaria',
            old_name='nombre',
            new_name='denominacion',
        ),
        migrations.AlterField(
            model_name='cuentabancaria',
            name='numero_cuenta',
            field=models.CharField(max_length=50),
        ),
        migrations.AlterField(
            model_name='cuentabancaria',
            name='denominacion',
            field=models.CharField(help_text='Ej: GNB Dólares', max_length=100),
        ),
        migrations.AlterField(
            model_name='cuentabancaria',
            name='banco',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='conciliacion.banco'),
        ),
        migrations.AlterField(
            model_name='cuentabancaria',
            name='tipo_cuenta',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='conciliacion.tipocuenta'),
        ),
        migrations.AlterField(
            model_name='cuentabancaria',
            name='moneda',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='conciliacion.moneda'),
        ),
        migrations.AddField(
            model_name='cuentabancaria',
            name='saldo_inicial',
            field=models.DecimalField(decimal_places=2, default=0.0, max_digits=18),
        ),
    ]
