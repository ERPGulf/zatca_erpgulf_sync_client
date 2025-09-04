
# import frappe
# import requests
# import json
# from urllib.parse import urlencode

# @frappe.whitelist()
# def sales_invoice_on_submit(doc, method=None):
#     """
#     Called when Sales Invoice is submitted.
#     Collects required fields and posts to external ZATCA API.
#     """
#     try:
#         # Load settings
#         settings = frappe.get_single("Zatca Sync Setting Page")
#         if not settings.url_for_submit_invoice:
#             frappe.throw("ZATCA Submit URL not configured in Zatca Sync Setting Page")

#         if not settings.user_invoice_number:
#             frappe.throw("User Invoice Number not configured in Zatca Sync Setting Page")

#         # Take and increment user_invoice_number
#          # auto increment
    
#         custom_user_invoice_number = settings.user_invoice_number
#         # Build final URL with custom_user_invoice_number param
#         base_url = settings.url_for_submit_invoice
#         params = {"custom_user_invoice_number": custom_user_invoice_number}
#         final_url = f"{base_url}?{urlencode(params)}"

#         # Prepare payload (without invoice number, since it's in URL)
#         payload = {
#             "customer_name": doc.customer_name,
#             "custom_user_invoice_number" : custom_user_invoice_number ,
#             "tax_id": doc.tax_id or "",
#             "posting_date": str(doc.posting_date),
#             "due_date": str(doc.due_date),
#             "discount_amount": doc.discount_amount or 0,
#             "tax_category": doc.tax_category or "Standard",
#             "exemption_reason_code": settings.exemption_reason_code or "",
#             "is_b2c": bool(doc.is_pos),  
#             "is_return": 1 if doc.is_return else 0,
#             "return_against": doc.return_against,
#             "items": [],
#             "taxes": []
#         }

#         # Add items (income account from settings)
#         for row in doc.items:
#             payload["items"].append({
#                 "item_name": row.item_name,
#                 "quantity": row.qty,
#                 "rate": row.rate,
#                 "income_account": settings.income_account or "",
#                 "description": row.description,
#                 "discount_amount": row.discount_amount or 0,
#                 "item_tax_template": row.item_tax_template
#             })

#         # Add taxes (account head from settings)
#         for tax in doc.taxes:
#             payload["taxes"].append({
#                 "charge_type": tax.charge_type,
#                 "account_head": settings.account_head or "",
#                 "rate": tax.rate,
#                 "description": tax.description,
#                 "included_in_print_rate": tax.included_in_print_rate
#             })

#         # Send request to external ZATCA server
#         headers = {"Content-Type": "application/json"}
#         response = requests.post(
#             final_url,
#             headers=headers,
#             data=json.dumps(payload),
#             timeout=30
#         )

#         if response.status_code != 200:
#             frappe.log_error(f"ZATCA Submit Failed: {response.text}", "ZATCA Submit Error")
#             frappe.throw(f"Failed to sync with ZATCA: {response.text}")

#         frappe.logger().info(f"ZATCA Submit Success: {response.text}")
#         return response.json()

#     except Exception:
#         frappe.log_error(frappe.get_traceback(), "ZATCA Invoice Submit Error")
#         raise
import base64
import re
import json
import requests
from urllib.parse import urlencode
import frappe
import uuid

@frappe.whitelist()
def sales_invoice_on_submit(doc, method=None):
    try:
        settings = frappe.get_single("Zatca Sync Setting Page")

        if not settings.url_for_submit_invoice:
            frappe.throw("ZATCA Submit URL not configured")
        if not settings.user_invoice_number:
            frappe.throw("User Invoice Number not configured")

        # custom_user_invoice_number = settings.user_invoice_number
        custom_user_invoice_number = str(uuid.uuid4())
        settings.user_invoice_number = custom_user_invoice_number
        settings.save(ignore_permissions=True)
        
        base_url = settings.url_for_submit_invoice
        params = {"custom_user_invoice_number": custom_user_invoice_number}
        final_url = f"{base_url}?{urlencode(params)}"
        customer_doc = frappe.get_doc("Customer", doc.customer_name)
        customer_tax_id = customer_doc.tax_id or ""
        customer_buyer_id_type = customer_doc.custom_buyer_id_type or ""
        customer_buyer_id = customer_doc.custom_buyer_id or ""

        # Build payload
        payload = {
            "customer_name": doc.customer_name,
            "custom_buyer_id_type": customer_buyer_id_type,
            "custom_buyer_id": customer_buyer_id,
            "custom_user_invoice_number": custom_user_invoice_number,
            "tax_id": customer_tax_id,
            "posting_date": str(doc.posting_date),
            "due_date": str(doc.due_date),
            "discount_amount": doc.discount_amount or 0,
            "tax_category": doc.custom_zatca_tax_category or "Standard",
            "exemption_reason_code": doc.custom_exemption_reason_code or "",
            "is_b2c": bool(doc.custom_b2c),
            "is_return": 1 if doc.is_return else 0,
            "return_against": doc.return_against,
            "items": [],
            "taxes": []
        }
        
        for row in doc.items:
            payload["items"].append({
                "item_name": row.item_name,
                "quantity": row.qty,
                "rate": row.rate,
                "income_account": settings.income_account or "",
                "description": row.description,
                "discount_amount": row.discount_amount or 0,
                "item_tax_template": row.item_tax_template
            })

        for tax in doc.taxes:
            payload["taxes"].append({
                "charge_type": tax.charge_type,
                "account_head": settings.account_head or "",
                "rate": tax.rate,
                "description": tax.description,
                "included_in_print_rate": tax.included_in_print_rate
            })

        # Send request
        
        headers = {"Content-Type": "application/json"}
        response = requests.post(final_url, headers=headers, data=json.dumps(payload), timeout=30)
        # frappe.throw(str(response.text))

        if response.status_code != 200:
            frappe.throw(f"Failed to sync with ZATCA: {response.text}")

        resp_json = response.json()
        data = resp_json.get("data", {})
        match = re.search(r'ZATCA Response:\s*({.*})', data["zatca_full_response"], re.DOTALL)
        doc.db_set("custom_zatca_full_response", data["zatca_full_response"])
        if match:
                zatca_json = json.loads(match.group(1))

                # ✅ If error field exists → FAILED
                if "errors" in zatca_json or "error" in zatca_json:
                    doc.db_set("custom_zatca_status", "FAILED")

                # ✅ Otherwise check B2C flag
                elif doc.custom_b2c:
                    doc.db_set("custom_zatca_status", "REPORTED")
                else:
                    doc.db_set("custom_zatca_status", "CLEARED")
        else:
                # Couldn’t parse JSON, mark FAILED
                doc.db_set("custom_zatca_status", "FAILED")


        frappe.msgprint(f"ZATCA Response: {frappe.as_json(data, indent=2)}")

        # --- ✅ Attach XML cleared invoice ---
        
        file_doc=None
        if "xml" in data and data["xml"]:
            file_doc = frappe.get_doc({
                "doctype": "File",
                "file_name": f"ZATCA_XML_{doc.name}.xml",
                "is_private": 1,
                "attached_to_doctype": doc.doctype,
                "attached_to_name": doc.name,
                "content": data["xml"]   # direct XML string from response
            })
        file_doc.insert(ignore_permissions=True)

        if file_doc:
            doc.db_set("custom_ksa_einvoicing_xml", file_doc.file_url)

        # --- ✅ Attach QR as link (no decoding, just use qr_image directly) ---
        if "qr_image" in data and data["qr_image"]:
            qr_file = frappe.get_doc({
                "doctype": "File",
                "file_name": f"QR_{doc.name}.png",
                "is_private": 1,
                "attached_to_doctype": doc.doctype,
                "attached_to_name": doc.name,
                "file_url": data["qr_image"]   # attach QR link directly
            })
            qr_file.insert(ignore_permissions=True)

        frappe.db.commit()

# Save response in log
        save_zatca_response(doc, data, status="Success" if response.status_code == 200 else "Failed")

        return resp_json

    except Exception:
        frappe.log_error(frappe.get_traceback(), "ZATCA Invoice Submit Error")
        raise

@frappe.whitelist()
def resubmit_sales_invoice(docname):
    """Manual resubmission to ZATCA from custom button."""
    doc = frappe.get_doc("Sales Invoice", docname)
    # Reuse the same function
    return sales_invoice_on_submit(doc, method="manual_resubmit")
def save_zatca_response(doc, response_data, status="Success"):
    try:
        log = frappe.get_doc({
            "doctype": "Zatca Sync Client Log",
            "sales_invoice": doc.name,
            "response_data": frappe.as_json(response_data, indent=2),
            "status": status
        })
        log.insert(ignore_permissions=True)
        frappe.db.commit()
    except Exception:
        frappe.log_error(frappe.get_traceback(), "Failed to save ZATCA response")
import base64
import xml.dom.minidom

import base64
import xml.dom.minidom
import json
import re
import base64
import xml.dom.minidom
import json
import re
import frappe

def decode_invoice_xml(zatca_full_response: str):
    """Extract XML (already base64 encoded inside ZATCA response) and return pretty formatted XML."""
    try:
        # Extract JSON portion from zatca_full_response
        match = re.search(r'ZATCA Response:\s*({.*})', zatca_full_response, re.DOTALL)
        if not match:
            return None

        zatca_json = json.loads(match.group(1))

        # ✅ Directly take XML string (clearedInvoice / reportedInvoice / invoice)
        xml_b64 = zatca_json.get("clearedInvoice") or zatca_json.get("reportedInvoice") or zatca_json.get("invoice")
        if not xml_b64:
            return None

        # Decode base64 to XML string
        decoded_bytes = base64.b64decode(xml_b64)
        decoded_xml = decoded_bytes.decode("utf-8")

        # Pretty format XML
        dom = xml.dom.minidom.parseString(decoded_xml)
        return dom.toprettyxml(indent="  ").strip()

    except Exception:
        frappe.log_error(frappe.get_traceback(), "Failed to decode ZATCA invoice XML")
        return None
