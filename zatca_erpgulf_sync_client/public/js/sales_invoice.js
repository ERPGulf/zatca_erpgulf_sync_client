frappe.ui.form.on("Sales Invoice", {
    refresh: function(frm) {
        if (frm.doc.docstatus === 1) {
            frm.add_custom_button(__('Resubmit to ZATCA'), function() {
                frappe.call({
                    method: "zatca_erpgulf_sync_client.sync.resubmit_sales_invoice",
                    args: {
                        docname: frm.doc.name
                    },
                    freeze: true,
                    freeze_message: __("Resubmitting invoice to ZATCA..."),
                    callback: function(r) {
                        if (r.message) {
                            frappe.msgprint({
                                title: __("ZATCA Resubmission"),
                                indicator: "green",
                                message: __("Invoice resubmitted successfully! <br><br> Response:<br>") + 
                                          "<pre style='max-height:300px;overflow:auto;'>" + 
                                          JSON.stringify(r.message, null, 2) + 
                                          "</pre>"
                            });
                            frm.reload_doc();
                        }
                    }
                });
            });
        }
    }
});
