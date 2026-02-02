# Copyright 2026 - Le Filament (https://le-filament.com)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

from odoo import models


class StockLocation(models.Model):
    _inherit = "stock.location"

    def should_bypass_reservation(self):
        """
        Specific case for customer rental location which should not be really
        considered a customer location
        """
        self.ensure_one()
        if self == self.warehouse_id.rental_out_location_id:
            return False
        else:
            return super().should_bypass_reservation()
