# Copyright 2014-2021 Akretion (http://www.akretion.com)
# @author Alexis de Lattre <alexis.delattre@akretion.com>
# Copyright 2016-2021 Sodexis (http://sodexis.com)
# Copyright 2026- Le Filament (https://le-filament.com)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import logging

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_compare, float_is_zero

logger = logging.getLogger(__name__)


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    rental = fields.Boolean(compute="_compute_rental", store=True, precompute=True)
    rental_type = fields.Selection(
        [("new_rental", "New Rental"), ("rental_extension", "Rental Extension")],
    )
    extension_rental_id = fields.Many2one(
        "sale.rental",
        string="Rental to Extend",
        check_company=True,
    )
    rental_qty = fields.Float(
        string="Rental Quantity",
        digits="Product Unit of Measure",
        help="Indicate the number of items that will be rented.",
    )

    _sql_constraints = [
        (
            "rental_qty_positive",
            "CHECK(rental_qty >= 0)",
            "The rental quantity must be positive or null.",
        )
    ]

    @api.constrains(
        "rental_type",
        "extension_rental_id",
        "start_date",
        "end_date",
        "rental_qty",
        "product_uom_qty",
        "product_id",
    )
    def _check_sale_line_rental(self):
        for line in self:
            if line.rental_type == "rental_extension":
                if not line.extension_rental_id:
                    raise ValidationError(
                        self.env._(
                            "Missing 'Rental to Extend' on the sale order line "
                            "with rental service %s",
                            line.product_id.display_name,
                        )
                    )

                if line.rental_qty != line.extension_rental_id.rental_qty:
                    raise ValidationError(
                        self.env._(
                            "On the sale order line with rental service %(name)s, "
                            "you are trying to extend a rental with a rental "
                            "quantity %(qty)s that is different from the quantity "
                            "of the original rental %(rental_qty)s. "
                            "This is not supported.",
                            name=line.product_id.display_name,
                            qty=line.rental_qty,
                            rental_qty=line.extension_rental_id.rental_qty,
                        )
                    )
            if line.rental_type in ("new_rental", "rental_extension"):
                if not line.product_id.rented_product_id:
                    raise ValidationError(
                        self.env._(
                            "On the 'new rental' sale order line with product "
                            "'%s', we should have a rental service product !",
                            line.product_id.display_name,
                        )
                    )

                if not line.product_uom or float_is_zero(
                    line.product_uom_qty, precision_rounding=line.product_uom.rounding
                ):
                    raise ValidationError(
                        self.env._("Quantity (items) must be greater than 0.")
                    )

    def _prepare_rental(self):
        self.ensure_one()
        return {"start_order_line_id": self.id}

    def _prepare_new_rental_procurement_values(self, group=False):
        vals = {
            "company_id": self.order_id.company_id,
            "group_id": group,
            "sale_line_id": self.id,
            "date_planned": self.start_date,
            "route_ids": self.route_id or self.order_id.warehouse_id.rental_route_id,
            "warehouse_id": self.order_id.warehouse_id or False,
            "partner_id": self.order_id.partner_shipping_id.id,
        }
        return vals

    def _run_rental_procurement(self, vals):
        self.ensure_one()
        procurements = [
            self.env["procurement.group"].Procurement(
                self.product_id.rented_product_id,
                self.rental_qty,
                self.product_id.rented_product_id.uom_id,
                self.order_id.warehouse_id.rental_out_location_id,
                self.name,
                self.order_id.name,
                self.order_id.company_id,
                vals,
            )
        ]
        self.env["procurement.group"].run(procurements)

    def _create_sale_rental(self, order_line):
        existing_rental = self.env["sale.rental"].search(
            [
                ("start_order_line_id", "=", order_line.id),
            ],
            limit=1,
        )

        if not existing_rental:
            self.env["sale.rental"].create(order_line._prepare_rental())

    def _action_launch_stock_rule(self, previous_product_uom_qty=False):
        errors = []
        for line in self:
            if line.rental_type == "new_rental" and line.product_id.rented_product_id:
                group = line.order_id.procurement_group_id
                if not group:
                    group = self.env["procurement.group"].create(
                        {
                            "name": line.order_id.name,
                            "move_type": line.order_id.picking_policy,
                            "sale_id": line.order_id.id,
                            "partner_id": line.order_id.partner_shipping_id.id,
                        }
                    )
                    line.order_id.procurement_group_id = group

                vals = line._prepare_new_rental_procurement_values(group)
                try:
                    line._run_rental_procurement(vals)
                except UserError as error:
                    errors.append(str(error))

                self._create_sale_rental(line)

            elif (
                line.rental_type == "rental_extension"
                and line.product_id.rented_product_id
                and line.extension_rental_id
                and line.extension_rental_id.in_move_id
            ):
                end_datetime = fields.Datetime.to_datetime(line.end_date)
                line.extension_rental_id.in_move_id.write(
                    {
                        "date": end_datetime,
                    }
                )

        if errors:
            raise UserError("\n".join(errors))

        # call super() at the end, to make procurement_jit work
        res = super()._action_launch_stock_rule(
            previous_product_uom_qty=previous_product_uom_qty
        )
        # Eventually we need to create incoming picking for returning rented products
        groups = self.mapped("order_id.procurement_group_id")
        groups.stock_move_ids._push_apply()
        return res

    def _prepare_procurement_values(self, group_id=False):
        """
        Overriding this function to changethe route
        on selling rental product
        """
        vals = super()._prepare_procurement_values(group_id=group_id)
        return vals

    @api.depends("product_id")
    def _compute_rental(self):
        for line in self:
            if line.product_id and line.product_id.rented_product_id:
                line.rental = True
                if not line.rental_type:
                    line.rental_type = "new_rental"
            else:
                line.rental = False
                line.rental_type = False
                line.rental_qty = 0
                line.extension_rental_id = False

    @api.onchange("product_id", "rental_qty")
    def rental_product_id_change(self):
        res = {}
        if (
            self.rental
            and self.rental_type == "new_rental"
            and self.rental_qty
            and self.order_id.warehouse_id
        ):
            product_uom = self.product_id.rented_product_id.uom_id
            warehouse = self.order_id.warehouse_id
            rental_in_location = warehouse.rental_in_location_id
            rented_product_ctx = self.with_context(
                location=rental_in_location.id
            ).product_id.rented_product_id
            in_location_available_qty = (
                rented_product_ctx.qty_available - rented_product_ctx.outgoing_qty
            )
            compare_qty = float_compare(
                in_location_available_qty,
                self.rental_qty,
                precision_rounding=product_uom.rounding,
            )
            if compare_qty == -1:
                res["warning"] = {
                    "title": self.env._("Not enough stock !"),
                    "message": self.env._(
                        "You want to rent %(rental_qty).2f  %(uom_name)s but "
                        "you only have %(available_qty).2f %(uom_name)s "
                        "currently available on the  stock location "
                        "'%(rental_name)s' ! Make sure that you get some "
                        "units back in the mean time or re-supply the "
                        "stock location '%(rental_name)s'.",
                        rental_qty=self.rental_qty,
                        uom_name=product_uom.name,
                        available_qty=in_location_available_qty,
                        rental_name=rental_in_location.name,
                    ),
                }
        return res

    @api.onchange("extension_rental_id")
    def extension_rental_id_change(self):
        if (
            self.product_id
            and self.rental_type == "rental_extension"
            and self.extension_rental_id
        ):
            if self.extension_rental_id.rental_product_id != self.product_id:
                raise UserError(
                    self.env._(
                        "The Rental Service of the Rental Extension you just "
                        "selected is '%s' and it's not the same as the "
                        "Product currently selected in this Sale Order Line.",
                        self.extension_rental_id.rental_product_id.display_name,
                    )
                )

            self.product_uom_qty = (
                self.extension_rental_id.start_order_line_id.product_uom_qty
            )

            initial_end_date = self.extension_rental_id.end_date
            if initial_end_date:
                self.start_date = initial_end_date + relativedelta(seconds=1)

            self.rental_qty = self.extension_rental_id.rental_qty

    @api.onchange("rental_type")
    def rental_type_change(self):
        if self.rental_type == "new_rental":
            self.extension_rental_id = False
