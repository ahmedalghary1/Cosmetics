from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand


ROLE_PERMISSIONS = {
    "Super Admin": ["*"],
    "Orders Manager": [
        "orders.view_order", "orders.view_orderitem", "orders.transition_order",
        "orders.view_payment_receipt",
        "orders.view_inventoryreservation", "orders.view_orderauditlog",
        "orders.view_returnrequest", "orders.change_returnrequest",
    ],
    "Accountant": [
        "orders.view_order", "orders.view_orderitem", "orders.verify_payment",
        "orders.view_payment_receipt", "orders.view_financial_reports",
        "orders.view_coupon", "orders.view_couponredemption", "orders.view_returnrequest",
    ],
    "Catalog Manager": [
        "products.add_product", "products.change_product", "products.delete_product", "products.view_product",
        "products.add_category", "products.change_category", "products.delete_category", "products.view_category",
        "products.add_productvariant", "products.change_productvariant", "products.delete_productvariant", "products.view_productvariant",
        "products.add_variantoption", "products.change_variantoption", "products.view_variantoption",
        "products.add_inventorybatch", "products.change_inventorybatch", "products.view_inventorybatch",
        "core.add_offer", "core.change_offer", "core.delete_offer", "core.view_offer",
    ],
    "Content Manager": [
        "core.add_banner", "core.change_banner", "core.delete_banner", "core.view_banner",
        "core.add_contentpage", "core.change_contentpage", "core.delete_contentpage", "core.view_contentpage",
        "core.add_socialgalleryimage", "core.change_socialgalleryimage", "core.delete_socialgalleryimage", "core.view_socialgalleryimage",
        "core.add_routinestep", "core.change_routinestep", "core.delete_routinestep", "core.view_routinestep",
    ],
    "Customer Support": [
        "orders.view_order", "orders.view_orderitem", "orders.view_returnrequest",
        "core.view_contactmessage", "core.change_contactmessage",
        "auth.view_user",
    ],
}


class Command(BaseCommand):
    help = "Create/update least-privilege dashboard roles. Safe to run repeatedly."

    def handle(self, *args, **options):
        all_permissions = Permission.objects.select_related("content_type")
        by_name = {
            f"{permission.content_type.app_label}.{permission.codename}": permission
            for permission in all_permissions
        }
        for role_name, permission_names in ROLE_PERMISSIONS.items():
            group, _ = Group.objects.get_or_create(name=role_name)
            permissions = list(by_name.values()) if permission_names == ["*"] else [
                by_name[name] for name in permission_names if name in by_name
            ]
            group.permissions.set(permissions)
            self.stdout.write(self.style.SUCCESS(f"{role_name}: {len(permissions)} permissions"))
