"""SMTP provider presets for the guided e-mail setup (wave 3b W3-MAIL; docs/deploy/email.md).

Each preset fills host / port / TLS mode / sign-in method and lists, in Turkish and English, what to create in the
provider's console. ``spf_include`` and ``dkim_selectors`` drive the DNS check of the from-domain
(:mod:`app.services.mail_dns`). Values were checked against the providers' public documentation in October 2026:

* Microsoft 365: Exchange Online turns Basic authentication (username + password) for SMTP AUTH off by default
  from December 2026 (message center MC786329; docs/design/v3/integrations.md §7.1); the preset is OAuth2 (XOAUTH2)
  with an app registration (client credentials, ``SMTP.SendAsApp``).
* ``abroad``: the provider's servers are outside Türkiye; saving it needs the KVKK md. 9 acknowledgement
  (integrations.md §7.1), recorded with the administrator's name and the date (``smtp.abroad_ack``).
* Google: an app password needs 2-Step Verification; OAuth2 (scope ``https://mail.google.com/``) works for
  Workspace and Gmail accounts.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class Step:
    tr: str
    en: str
    #: a value to copy into the provider console (shown with a copy button)
    copy: str | None = None


@dataclass(frozen=True)
class Preset:
    id: str
    label: str
    host: str
    port: int
    security: str  # starttls | ssl | none
    auth_mode: str  # password | xoauth2 | none
    username_hint_tr: str
    username_hint_en: str
    password_label_tr: str = "Parola"
    password_label_en: str = "Password"
    oauth_provider: str = ""
    console_url: str = ""
    spf_include: tuple[str, ...] = ()
    dkim_selectors: tuple[str, ...] = ()
    #: host variants the admin can pick (region / EU endpoint)
    hosts: tuple[str, ...] = ()
    steps: tuple[Step, ...] = ()
    notes_tr: str = ""
    notes_en: str = ""
    extra: dict[str, Any] = field(default_factory=dict)
    #: servers outside Türkiye: the KVKK md. 9 acknowledgement is required (integrations.md §7.1)
    abroad: bool = False

    def out(self) -> dict[str, Any]:
        d = asdict(self)
        d["steps"] = [asdict(s) for s in self.steps]
        d["spf_include"] = list(self.spf_include)
        d["dkim_selectors"] = list(self.dkim_selectors)
        d["hosts"] = list(self.hosts) or [self.host]
        return d


S = Step
PRESETS: tuple[Preset, ...] = (
    Preset(
        id="google_app_password",
        label="Google Workspace / Gmail (uygulama şifresi)",
        host="smtp.gmail.com",
        port=587,
        security="starttls",
        auth_mode="password",
        username_hint_tr="Gönderen hesabın tam e-posta adresi",
        username_hint_en="The sending account's full e-mail address",
        password_label_tr="Uygulama şifresi (16 karakter)",
        password_label_en="App password (16 characters)",
        console_url="https://myaccount.google.com/apppasswords",
        spf_include=("_spf.google.com",),
        dkim_selectors=("google",),
        steps=(
            S("Gönderen hesapta 2 Adımlı Doğrulama'yı açın.", "Turn on 2-Step Verification for the sending account."),
            S(
                "myaccount.google.com/apppasswords sayfasında 'SmartSched' adlı bir uygulama şifresi oluşturun.",
                "Create an app password named 'SmartSched' at myaccount.google.com/apppasswords.",
                "SmartSched",
            ),
            S(
                "Kullanıcı adına tam e-posta adresini, parolaya 16 karakterlik uygulama şifresini boşluksuz "
                "yapıştırın.",
                "Paste the full e-mail address as the username and the 16-character app password without spaces.",
            ),
            S(
                "Workspace yöneticisi: Yönetici Konsolu > Uygulamalar > Google Workspace > Gmail > Kimlik doğrulama "
                "bölümünde DKIM'i başlatın.",
                "Workspace admin: start DKIM under Admin console > Apps > Google Workspace > Gmail > Authenticate "
                "email.",
            ),
        ),
        notes_tr="Kurumda uygulama şifreleri kapalıysa OAuth2 ön ayarını kullanın.",
        notes_en="If app passwords are turned off in your organisation, use the OAuth2 preset.",
    ),
    Preset(
        id="google_oauth2",
        label="Google Workspace / Gmail (OAuth2)",
        host="smtp.gmail.com",
        port=587,
        security="starttls",
        auth_mode="xoauth2",
        oauth_provider="google",
        username_hint_tr="Gönderen hesabın tam e-posta adresi",
        username_hint_en="The sending account's full e-mail address",
        console_url="https://console.cloud.google.com/apis/credentials",
        spf_include=("_spf.google.com",),
        dkim_selectors=("google",),
        steps=(
            S(
                "Google Cloud Console > API'ler ve Hizmetler > Kimlik bilgileri bölümünde 'OAuth istemci kimliği' "
                "(Web uygulaması) oluşturun.",
                "In Google Cloud Console > APIs & Services > Credentials create an 'OAuth client ID' (Web "
                "application).",
            ),
            S(
                "Yetkili yönlendirme URI'si olarak OAuth Playground adresini ekleyin.",
                "Add the OAuth Playground as an authorised redirect URI.",
                "https://developers.google.com/oauthplayground",
            ),
            S(
                "OAuth Playground'da kendi istemci kimliğinizle şu kapsamı yetkilendirin ve yenileme jetonunu alın.",
                "In the OAuth Playground, authorise this scope with your own client and exchange it for a refresh "
                "token.",
                "https://mail.google.com/",
            ),
            S(
                "İstemci kimliği, istemci gizli anahtarı ve yenileme jetonunu buraya yapıştırın.",
                "Paste the client ID, client secret and refresh token here.",
            ),
        ),
    ),
    Preset(
        id="microsoft365_oauth2",
        label="Microsoft 365 / Exchange Online (OAuth2)",
        host="smtp.office365.com",
        port=587,
        security="starttls",
        auth_mode="xoauth2",
        oauth_provider="microsoft",
        username_hint_tr="Gönderen posta kutusunun adresi (ör. bildirim@uni.edu.tr)",
        username_hint_en="The sending mailbox's address (e.g. notifications@uni.edu.tr)",
        console_url="https://entra.microsoft.com/#view/Microsoft_AAD_RegisteredApps/ApplicationsListBlade",
        spf_include=("spf.protection.outlook.com",),
        dkim_selectors=("selector1", "selector2"),
        steps=(
            S(
                "Microsoft Entra yönetim merkezi > Uygulama kayıtları > Yeni kayıt: 'SmartSched Mail'.",
                "Microsoft Entra admin center > App registrations > New registration: 'SmartSched Mail'.",
                "SmartSched Mail",
            ),
            S(
                "API izinleri > Kuruluşumun kullandığı API'ler > Office 365 Exchange Online > Uygulama izni: "
                "SMTP.SendAsApp; ardından 'Yönetici onayı ver'.",
                "API permissions > APIs my organization uses > Office 365 Exchange Online > Application permission: "
                "SMTP.SendAsApp; then 'Grant admin consent'.",
                "SMTP.SendAsApp",
            ),
            S(
                "Sertifikalar ve gizli anahtarlar > Yeni istemci gizli anahtarı; değeri hemen kopyalayın.",
                "Certificates & secrets > New client secret; copy the value right away.",
            ),
            S(
                "Exchange Online PowerShell'de hizmet sorumlusunu kaydedin ve posta kutusuna izin verin.",
                "In Exchange Online PowerShell register the service principal and grant it the mailbox.",
                "New-ServicePrincipal -AppId <uygulama-kimliği> -ObjectId <kurumsal-uygulama-nesne-kimliği>; "
                "Add-MailboxPermission -Identity bildirim@uni.edu.tr -User <hizmet-sorumlusu-kimliği> -AccessRights "
                "FullAccess",
            ),
            S(
                "Posta kutusunda SMTP AUTH'u açın.",
                "Turn on SMTP AUTH for the mailbox.",
                "Set-CASMailbox -Identity bildirim@uni.edu.tr -SmtpClientAuthenticationDisabled $false",
            ),
            S(
                "Dizin (kiracı) kimliğini, uygulama (istemci) kimliğini ve gizli anahtarı buraya yapıştırın.",
                "Paste the directory (tenant) ID, the application (client) ID and the secret here.",
            ),
        ),
        notes_tr=(
            "Exchange Online, parola ile SMTP girişini (Basic auth) Aralık 2026'dan itibaren varsayılan olarak "
            "kapatıyor (MC786329); bu ön ayar OAuth2 kullanır. Gönderen adresine 'Farklı gönder' izni gerekir."
        ),
        notes_en=(
            "Exchange Online turns password SMTP (Basic auth) off by default from December 2026 (MC786329); this "
            "preset uses OAuth2. The from-address needs 'Send As' permission."
        ),
    ),
    Preset(
        id="amazon_ses",
        abroad=True,
        label="Amazon SES",
        host="email-smtp.eu-central-1.amazonaws.com",
        port=587,
        security="starttls",
        auth_mode="password",
        username_hint_tr="SES SMTP kullanıcı adı (IAM erişim anahtarı değil)",
        username_hint_en="The SES SMTP username (not an IAM access key)",
        password_label_tr="SES SMTP parolası",
        password_label_en="SES SMTP password",
        console_url="https://console.aws.amazon.com/ses/home#/smtp",
        spf_include=("amazonses.com",),
        hosts=(
            "email-smtp.eu-central-1.amazonaws.com",
            "email-smtp.eu-west-1.amazonaws.com",
            "email-smtp.eu-south-1.amazonaws.com",
            "email-smtp.us-east-1.amazonaws.com",
        ),
        steps=(
            S(
                "SES > Kimlikler: gönderen alan adınızı doğrulayın (Easy DKIM'in 3 CNAME kaydını DNS'e ekleyin).",
                "SES > Identities: verify your sending domain (add the 3 Easy DKIM CNAME records to DNS).",
            ),
            S("SES > SMTP ayarları > SMTP kimlik bilgileri oluştur.", "SES > SMTP settings > Create SMTP credentials."),
            S(
                "Hesap korumalı alandaysa (sandbox) üretim erişimi isteyin; yoksa yalnızca doğrulanmış adreslere "
                "gider.",
                "If the account is in the sandbox, request production access; otherwise mail only reaches verified "
                "addresses.",
            ),
        ),
        notes_tr="DKIM seçicileri SES'te rastgele jetonlardır: DNS denetimi için birini 'DKIM seçici' alanına yazın.",
        notes_en="SES DKIM selectors are random tokens: type one into 'DKIM selector' for the DNS check.",
    ),
    Preset(
        id="sendgrid",
        abroad=True,
        label="SendGrid (Twilio)",
        host="smtp.sendgrid.net",
        port=587,
        security="starttls",
        auth_mode="password",
        username_hint_tr="Kullanıcı adı her zaman: apikey",
        username_hint_en="The username is always: apikey",
        password_label_tr="API anahtarı (Mail Send izni)",
        password_label_en="API key (Mail Send permission)",
        console_url="https://app.sendgrid.com/settings/api_keys",
        spf_include=("sendgrid.net",),
        dkim_selectors=("s1", "s2"),
        extra={"username": "apikey"},
        steps=(
            S(
                "Settings > API Keys > Create API Key: 'Restricted', yalnızca Mail Send.",
                "Settings > API Keys > Create API Key: 'Restricted', Mail Send only.",
                "SmartSched",
            ),
            S(
                "Settings > Sender Authentication > Authenticate Your Domain: verilen CNAME kayıtlarını DNS'e ekleyin.",
                "Settings > Sender Authentication > Authenticate Your Domain: add the CNAME records to DNS.",
            ),
            S(
                "Kullanıcı adı 'apikey', parola API anahtarıdır.",
                "The username is 'apikey', the password the API key.",
                "apikey",
            ),
        ),
    ),
    Preset(
        id="mailgun",
        abroad=True,
        label="Mailgun",
        host="smtp.eu.mailgun.org",
        port=587,
        security="starttls",
        auth_mode="password",
        username_hint_tr="SMTP kullanıcısı, ör. postmaster@mg.uni.edu.tr",
        username_hint_en="The SMTP user, e.g. postmaster@mg.uni.edu.tr",
        console_url="https://app.mailgun.com/",
        spf_include=("mailgun.org",),
        dkim_selectors=("smtp", "mx", "k1", "pic"),
        hosts=("smtp.eu.mailgun.org", "smtp.mailgun.org"),
        steps=(
            S(
                "Sending > Domains > Add new domain (ör. mg.uni.edu.tr); TXT ve CNAME kayıtlarını DNS'e ekleyin.",
                "Sending > Domains > Add new domain (e.g. mg.uni.edu.tr); add the TXT and CNAME records to DNS.",
            ),
            S(
                "Domain settings > SMTP credentials: yeni SMTP kullanıcısı ve parolası oluşturun.",
                "Domain settings > SMTP credentials: create an SMTP user and password.",
            ),
            S(
                "Hesap AB bölgesindeyse smtp.eu.mailgun.org, değilse smtp.mailgun.org seçin.",
                "Pick smtp.eu.mailgun.org for an EU account, smtp.mailgun.org otherwise.",
            ),
        ),
    ),
    Preset(
        id="postmark",
        abroad=True,
        label="Postmark",
        host="smtp.postmarkapp.com",
        port=587,
        security="starttls",
        auth_mode="password",
        username_hint_tr="Sunucu API jetonu (kullanıcı adı ve parola aynı)",
        username_hint_en="The Server API token (same as username and password)",
        password_label_tr="Sunucu API jetonu",
        password_label_en="Server API token",
        console_url="https://account.postmarkapp.com/servers",
        spf_include=("spf.mtasv.net",),
        steps=(
            S(
                "Servers > (sunucunuz) > API Tokens: Server API token'ı kopyalayın.",
                "Servers > (your server) > API Tokens: copy the Server API token.",
            ),
            S(
                "Sender Signatures > Domains: alan adınızı ekleyin ve DKIM + Return-Path kayıtlarını DNS'e girin.",
                "Sender Signatures > Domains: add your domain and enter the DKIM + Return-Path records in DNS.",
            ),
            S("Kullanıcı adına ve parolaya aynı jetonu yapıştırın.", "Paste the same token as username and password."),
        ),
        notes_tr="Postmark DKIM seçicisi tarihli bir değerdir (ör. 20261017pm); DNS denetimi için yazın.",
        notes_en="The Postmark DKIM selector is dated (e.g. 20261017pm); type it for the DNS check.",
    ),
    Preset(
        id="brevo",
        abroad=True,
        label="Brevo (Sendinblue)",
        host="smtp-relay.brevo.com",
        port=587,
        security="starttls",
        auth_mode="password",
        username_hint_tr="SMTP girişi (SMTP ve API sayfasında görünür)",
        username_hint_en="The SMTP login (shown on the SMTP & API page)",
        password_label_tr="SMTP anahtarı",
        password_label_en="SMTP key",
        console_url="https://app.brevo.com/settings/keys/smtp",
        spf_include=("spf.brevo.com", "spf.sendinblue.com"),
        dkim_selectors=("brevo1", "brevo2", "mail"),
        steps=(
            S("SMTP ve API > SMTP: yeni bir SMTP anahtarı oluşturun.", "SMTP & API > SMTP: generate a new SMTP key."),
            S(
                "Gönderenler, Alan Adları > Alan adı ekle: DKIM ve DMARC kayıtlarını DNS'e girin.",
                "Senders, Domains > Add a domain: enter the DKIM and DMARC records in DNS.",
            ),
        ),
    ),
    Preset(
        id="yandex",
        label="Yandex 360",
        host="smtp.yandex.com",
        port=465,
        security="ssl",
        auth_mode="password",
        username_hint_tr="Tam e-posta adresi",
        username_hint_en="The full e-mail address",
        password_label_tr="Uygulama parolası",
        password_label_en="App password",
        console_url="https://id.yandex.com/security/app-passwords",
        spf_include=("_spf.yandex.net",),
        dkim_selectors=("mail",),
        steps=(
            S(
                "Yandex ID > Güvenlik > Uygulama parolaları: 'Posta' için bir parola oluşturun.",
                "Yandex ID > Security > App passwords: create a password for 'Mail'.",
            ),
            S(
                "Yandex 360 yönetim > Alan adları: DKIM kaydını DNS'e ekleyin.",
                "Yandex 360 admin > Domains: add the DKIM record to DNS.",
            ),
        ),
    ),
    Preset(
        id="resend",
        label="Resend",
        abroad=True,
        host="smtp.resend.com",
        port=587,
        security="starttls",
        auth_mode="password",
        username_hint_tr="Kullanıcı adı her zaman: resend",
        username_hint_en="The username is always: resend",
        password_label_tr="API anahtarı",
        password_label_en="API key",
        console_url="https://resend.com/api-keys",
        spf_include=("amazonses.com",),
        dkim_selectors=("resend",),
        hosts=("smtp.resend.com",),
        extra={"username": "resend"},
        steps=(
            S("API Keys > Create API Key: 'Sending access' izniyle.", "API Keys > Create API Key with 'Sending access'."),
            S(
                "Domains > Add Domain: verilen MX, SPF (send alt alanı) ve DKIM (resend._domainkey) kayıtlarını ekleyin.",
                "Domains > Add Domain: add the MX, SPF (send subdomain) and DKIM (resend._domainkey) records.",
            ),
            S("Kullanıcı adı 'resend', parola API anahtarıdır.", "The username is 'resend', the password the API key.", "resend"),
        ),
    ),
    Preset(
        id="google_relay",
        label="Google Workspace (SMTP aktarma hizmeti)",
        host="smtp-relay.gmail.com",
        port=587,
        security="starttls",
        auth_mode="none",
        username_hint_tr="IP izin listesiyle boş bırakın; SMTP kimlik doğrulaması seçildiyse Workspace hesabı",
        username_hint_en="Leave empty with an IP allow-list; a Workspace account if SMTP authentication is required",
        console_url="https://admin.google.com/ac/apps/gmail/routing",
        spf_include=("_spf.google.com",),
        dkim_selectors=("google",),
        steps=(
            S(
                "Yönetici Konsolu > Uygulamalar > Google Workspace > Gmail > Yönlendirme > SMTP aktarma hizmeti: "
                "'SmartSched' adında bir kural ekleyin.",
                "Admin console > Apps > Google Workspace > Gmail > Routing > SMTP relay service: add a rule "
                "named 'SmartSched'.",
                "SmartSched",
            ),
            S(
                "İzin verilen gönderenler: 'Yalnızca alan adlarımdaki adresler'; kimlik doğrulama: sunucunun IP adresi "
                "ya da SMTP kimlik doğrulaması; 'TLS şifrelemesi gerektir' açık.",
                "Allowed senders: 'Only addresses in my domains'; authentication: the server's IP address or SMTP "
                "authentication; 'Require TLS encryption' on.",
            ),
        ),
        notes_tr="Uygulama parolası, 2 adımlı doğrulaması açık hesapta üretilir; hesap parolası asla kullanılmaz.",
        notes_en="An app password is created on an account with 2-Step Verification; never the account password.",
    ),
    Preset(
        id="custom",
        label="Kurum sunucusu / diğer (ör. Türk Telekom kurumsal e-posta)",
        host="",
        port=587,
        security="starttls",
        auth_mode="password",
        username_hint_tr="Bilgi işlemin verdiği hesap",
        username_hint_en="The account your IT department gave you",
        steps=(
            S(
                "Bilgi işlemden (ya da e-posta sağlayıcınızdan) SMTP sunucu adını, bağlantı noktasını ve şifreleme "
                "türünü isteyin: genellikle 587 + STARTTLS ya da 465 + SSL/TLS.",
                "Ask your IT department (or e-mail provider) for the SMTP host, port and encryption: usually "
                "587 + STARTTLS or 465 + SSL/TLS.",
            ),
            S(
                "Gönderim için bir hesap (ör. bildirim@uni.edu.tr) ve bu sunucudan gönderme izni isteyin.",
                "Ask for a sending account (e.g. notifications@uni.edu.tr) and permission to send from this server.",
            ),
            S(
                "Alan adının SPF kaydına sunucunun adresini, DKIM için seçiciyi ve bir DMARC kaydını eklemelerini "
                "isteyin.",
                "Ask them to add the server to the domain's SPF record, a DKIM selector and a DMARC record.",
            ),
        ),
        notes_tr="Kimlik doğrulamasız iç aktarma (relay) kullanılıyorsa oturum açma yöntemini 'Yok' seçin.",
        notes_en="For an internal relay without authentication choose 'None' as the sign-in method.",
    ),
)
BY_ID: dict[str, Preset] = {p.id: p for p in PRESETS}


def presets_out() -> list[dict[str, Any]]:
    return [p.out() for p in PRESETS]


def get(preset_id: str | None) -> Preset | None:
    return BY_ID.get(preset_id or "")
