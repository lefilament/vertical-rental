# Copyright 2014-2021 Akretion France (http://www.akretion.com)
# @author Alexis de Lattre <alexis.delattre@akretion.com>
# Copyright 2016-2021 Sodexis (http://sodexis.com)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import api, fields, models


class ProductTemplate(models.Model):
    _inherit = "product.template"

    rented_product_tmpl_id = fields.Many2one(
        "product.template",
        compute="_compute_rented_product_tmpl_id",
        string="Rented Product",
        inverse="_inverse_rented_product_tmpl_id",
        store=True,
        domain=[("type", "=", "consu")],
    )
    rental_service_tmpl_ids = fields.One2many(
        "product.template", "rented_product_tmpl_id", string="Rental Services"
    )

    @api.depends("product_variant_ids", "product_variant_ids.rented_product_id")
    def _compute_rented_product_tmpl_id(self):
        unique_variants = self.filtered(
            lambda template: len(template.product_variant_ids) == 1
        )
        for template in unique_variants:
            variant_id = template.product_variant_ids
            template.rented_product_tmpl_id = (
                variant_id.rented_product_id.product_tmpl_id.id
                if variant_id.rented_product_id
                else False
            )
        for template in self - unique_variants:
            template.rented_product_tmpl_id = False

    def _inverse_rented_product_tmpl_id(self):
        for template in self:
            if len(template.product_variant_ids) == 1:
                template.product_variant_ids.rented_product_id = (
                    template.rented_product_tmpl_id.product_variant_ids[0].id
                )
