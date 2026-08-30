from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("products", "0008_backinstocksubscription"),
    ]

    operations = [
        migrations.CreateModel(
            name="ProductCategoryOrder",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("order", models.PositiveIntegerField(default=0, verbose_name="الترتيب")),
                ("category", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="product_display_orders", to="products.category", verbose_name="القسم")),
                ("product", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="category_display_orders", to="products.product", verbose_name="المنتج")),
            ],
            options={
                "verbose_name": "ترتيب منتج داخل قسم",
                "verbose_name_plural": "ترتيب المنتجات داخل الأقسام",
                "ordering": ["order", "product_id"],
                "indexes": [models.Index(fields=["category", "order"], name="products_pr_categor_154431_idx")],
                "constraints": [models.UniqueConstraint(fields=("category", "product"), name="unique_product_order_per_category")],
            },
        ),
    ]
