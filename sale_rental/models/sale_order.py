# Copyright 2014-2021 Akretion (http://www.akretion.com)
# @author Alexis de Lattre <alexis.delattre@akretion.com>
# Copyright 2016-2021 Sodexis (http://sodexis.com)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import logging

from odoo import models

logger = logging.getLogger(__name__)


class SaleOrder(models.Model):
    _inherit = "sale.order"

    def action_cancel(self):
        """
        When the user cancels a rental extension, Odoo writes the initial
        end date on the return picking
        """
        res = super().action_cancel()
        for order in self:
            for line in order.order_line.filtered(
                lambda lin: lin.rental_type == "rental_extension"
                and lin.extension_rental_id
            ):
                initial_end_date = line.extension_rental_id.end_datetime
                line.extension_rental_id.in_move_id.write(
                    {
                        "date": initial_end_date,
                    }
                )
        return res
