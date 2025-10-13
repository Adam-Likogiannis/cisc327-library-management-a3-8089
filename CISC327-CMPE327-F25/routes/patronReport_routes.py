"""
Search Routes - Patron report status functionality
"""

from flask import Blueprint, render_template, request, flash
from library_service import get_patron_status_report

patrons_bp = Blueprint('patrons', __name__)

@patrons_bp.route('/patron_status_report')
def patron_status_report():
    """
    Show patron account data.
    Web interface for R7
    """

    patron_id = request.args.get('q', '').strip()

    if not patron_id:
        return render_template('patron_report.html', search_term='', report=None)

    # Call the service function
    report = get_patron_status_report(patron_id)

    return render_template('patron_report.html', search_term=patron_id, report=report)
