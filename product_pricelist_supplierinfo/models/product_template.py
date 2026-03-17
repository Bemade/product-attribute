# Copyright 2018 Tecnativa - Vicent Cubells
# Copyright 2018 Tecnativa - Pedro M. Baeza
# Copyright 2019-2025 Tecnativa - Carlos Dauden
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from datetime import datetime

from odoo import fields, models, tools


class ProductTemplate(models.Model):
    _inherit = "product.template"

    def _get_supplierinfo_pricelist_price(
        self,
        rule,
        date=None,
        quantity=None,
        product_id=None,
        uom=None,
    ):
        """Method for getting the price from supplier info."""
        self.ensure_one()
        price = 0.0
        product = self.product_variant_id
        if product_id:
            product = product.browse(product_id)
        if rule.no_supplierinfo_min_quantity:
            # No matter which minimum qty, we'll get every seller. We set a
            # number absurdidly high
            quantity = 1e9
        # The product_variant_id returns empty recordset if template is not
        # active, so we must ensure variant exists or _select_seller fails.
        if product:
            if isinstance(date, datetime):
                date = date.date()
            seller = product.with_context(
                override_min_qty=rule.no_supplierinfo_min_quantity
            )._select_seller(
                # For a public user this record could be not accessible, but we
                # need to get the price anyway
                partner_id=self.env.context.get(
                    "force_filter_supplier_id", rule.sudo().filter_supplier_id
                ),
                quantity=quantity,
                date=date,
                uom_id=uom or self.uom_id,
            )
            if seller:
                price = seller._get_supplierinfo_pricelist_price(
                    rule.no_supplierinfo_discount,
                    ignore_margin=rule.ignore_supplierinfo_margin,
                )
                if not price:
                    return price
                # We need to convert the price if the pricelist and seller
                # have different currencies so the price has the pricelist
                # currency
                if rule.currency_id != seller.currency_id:
                    convert_date = date or self.env.context.get(
                        "date", fields.Date.today()
                    )
                    price = seller.currency_id._convert(
                        price, rule.currency_id, seller.company_id, convert_date
                    )

                # We have to replicate this logic in this method as pricelist
                # method are atomic and we can't hack inside.
                # Verbatim copy of part of product.pricelist.item._compute_price.
                #
                # Note: price_discounted (default path) is already converted
                # from seller UoM to product UoM by product.supplierinfo.
                # When no_supplierinfo_discount is True, raw seller.price is
                # in seller UoM, so we must convert seller→product first.
                product_uom = self.uom_id
                if (
                    rule.no_supplierinfo_discount
                    and seller.product_uom_id != product_uom
                ):
                    price = seller.product_uom_id._compute_price(price, product_uom)
                # Now price is in product UoM; convert to target UoM
                target_uom = uom or product_uom
                if product_uom != target_uom:
                    convert = lambda p: product_uom._compute_price(p, target_uom)
                else:
                    convert = lambda p: p
                price = convert(price)
                price_limit = price
                price = (price - (price * (rule.price_discount / 100))) or 0.0
                if rule.price_round:
                    price = tools.float_round(
                        price, precision_rounding=rule.price_round
                    )
                if rule.price_surcharge:
                    price += convert(rule.price_surcharge)
                if rule.price_min_margin:
                    price = max(price, price_limit + convert(rule.price_min_margin))
                if rule.price_max_margin:
                    price = min(price, price_limit + convert(rule.price_max_margin))
        return price

    def _price_compute(
        self, price_type, uom=None, currency=None, company=False, date=False
    ):
        """Return dummy not falsy prices when computation is done from supplier
        info for avoiding error on super method. We will later fill these with
        correct values.
        """
        if price_type == "supplierinfo":
            return dict.fromkeys(self.ids, 1.0)
        return super()._price_compute(
            price_type, uom=uom, currency=currency, company=company, date=date
        )
