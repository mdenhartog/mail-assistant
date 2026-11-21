"""Domains that may not be listed as a domain sender entry (INT-008, D15, C-4).

A domain entry for a public mailbox provider would file mail from every customer of that provider, and one for a
multi-tenant sending platform would trust text written by anyone who uses the platform. A full address on such a
domain stays allowed. A name here also refuses its subdomains (``tenant.onmicrosoft.com``).
"""

PUBLIC_MAILBOX_DOMAINS = frozenset(
    {
        "aol.com",
        "casema.nl",
        "chello.nl",
        "fastmail.com",
        "gmail.com",
        "gmx.com",
        "gmx.de",
        "gmx.net",
        "googlemail.com",
        "hetnet.nl",
        "hey.com",
        "home.nl",
        "hotmail.com",
        "hotmail.nl",
        "icloud.com",
        "kpnmail.nl",
        "live.com",
        "live.nl",
        "mac.com",
        "mail.com",
        "mail.ru",
        "me.com",
        "msn.com",
        "online.nl",
        "outlook.com",
        "outlook.nl",
        "planet.nl",
        "pm.me",
        "proton.me",
        "protonmail.com",
        "quicknet.nl",
        "rocketmail.com",
        "t-online.de",
        "telenet.be",
        "tuta.com",
        "tutanota.com",
        "upcmail.nl",
        "web.de",
        "xs4all.nl",
        "yahoo.com",
        "yahoo.nl",
        "yandex.com",
        "yandex.ru",
        "ymail.com",
        "zoho.com",
        "ziggo.nl",
    }
)

SENDING_PLATFORM_DOMAINS = frozenset(
    {
        "amazonses.com",
        "beehiiv.com",
        "brevo.com",
        "campaign-archive.com",
        "ccsend.com",
        "constantcontact.com",
        "createsend.com",
        "elasticemail.com",
        "exacttarget.com",
        "googlegroups.com",
        "groups.io",
        "hubspotemail.net",
        "klaviyomail.com",
        "list-manage.com",
        "mailchimp.com",
        "mailchimpapp.net",
        "mailgun.net",
        "mailgun.org",
        "mailjet.com",
        "mandrillapp.com",
        "mcdlv.net",
        "mcsv.net",
        "mjt.lu",
        "mtasv.net",
        "onmicrosoft.com",
        "postmarkapp.com",
        "rsgsv.net",
        "sendgrid.com",
        "sendgrid.net",
        "sendinblue.com",
        "smtp2go.com",
        "sparkpost.com",
        "sparkpostmail.com",
        "substack.com",
        "yahoogroups.com",
    }
)

REFUSED_DOMAINS = PUBLIC_MAILBOX_DOMAINS | SENDING_PLATFORM_DOMAINS


def is_refused_domain(domain: str) -> bool:
    """Return whether a canonical (lower-case A-label) domain is a refused domain or a subdomain of one.

    Args:
        domain: The domain of an entry, as ``parse_entry`` returns it.

    Returns:
        True when a domain entry for it must be refused.
    """
    labels = domain.split(".")
    return any(".".join(labels[i:]) in REFUSED_DOMAINS for i in range(len(labels)))
