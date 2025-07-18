// Copyright (c) 2025, HKSoHo and contributors
// For license information, please see license.txt

frappe.ui.form.on("Partner", {
    onload(frm){
        console.log("on_load running")
    },
    setup(frm){
        console.log("setup running")
    },
	refresh(frm) {
        console.log("refresh running")
        //if (frm.doc.status !== "Accepted"){}
        frm.add_custom_button("Accept",()=>{
            console.log("Accept clicked")
            frappe.show_alert("It works");
            //frm.set_value("status","Accepted")
            //frm.save();
        },"Action")
                frm.add_custom_button("Reject",()=>{
            console.log("Reject clicked")
            frappe.show_alert("It works");
            //frm.set_value("status","Accepted")
            //frm.save();
        },"Action")
	},
    // status(frm){
    //     console.log("status change.")
    // }
});
