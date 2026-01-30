# Copyright 2014-2021 Akretion France (http://www.akretion.com)
# @author Alexis de Lattre <alexis.delattre@akretion.com>
# Copyright 2016-2021 Sodexis (http://sodexis.com)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import api, fields, models
from odoo.exceptions import ValidationError


class ProductProduct(models.Model):
    _inherit = "product.product"

    # Link rental service -> rented HW product
    rented_product_id = fields.Many2one(
        "product.product",
        string="Related Rented Product",
        domain=[("type", "=", "consu")],
    )
    # Link rented HW product -> rental service
    rental_service_ids = fields.One2many(
        "product.product", "rented_product_id", string="Related Rental Services"
    )

    @api.constrains("rented_product_id", "must_have_dates", "type")
    def _check_rental(self):
        for product in self:
            if product.rented_product_id:
                if product.type != "service":
                    raise ValidationError(
                        self.env._(
                            "The rental product '%s' must be of type 'Service'.",
                            product.name,
                        )
                    )
                if not product.must_have_dates:
                    raise ValidationError(
                        self.env._(
                            "The rental product '%s' must have the option "
                            "'Must Have Start and End Dates' checked.",
                            product.name,
                        )
                    )
