import frappe

TOKEN = "__CHAT_TOKEN__"
FUNNEL = "__FUNNEL_BASE__"  # substituted at deploy (like __CHAT_TOKEN__) — no hardcoded host
ROUTE = "agent-chat"

iframe_src = f"{FUNNEL}/chat?chat_token={TOKEN}"
html = f"""
<div style="position:fixed;inset:0;display:flex;flex-direction:column;background:#0b0b0d;">
  <iframe
    src="{iframe_src}"
    title="Agent Chat"
    allow="clipboard-write; clipboard-read; microphone"
    style="flex:1 1 auto;width:100%;height:100%;border:0;display:block;">
  </iframe>
</div>
"""

existing = frappe.db.exists("Web Page", {"route": ROUTE})
if existing:
    doc = frappe.get_doc("Web Page", existing)
    print("updating existing Web Page:", existing)
else:
    doc = frappe.new_doc("Web Page")
    print("creating new Web Page")

doc.title = "Agent Chat"
doc.route = ROUTE
doc.published = 1
doc.content_type = "HTML"
doc.main_section_html = html
# Render edge-to-edge: no page header/sidebar/breadcrumbs.
doc.show_title = 0
if hasattr(doc, "full_width"):
    doc.full_width = 1
doc.flags.ignore_permissions = True
doc.save(ignore_permissions=True)
frappe.db.commit()

print("OK route=/", doc.route, "published=", doc.published, "name=", doc.name)
print("URL: https://crm.forschfrontiers.com/" + doc.route)
