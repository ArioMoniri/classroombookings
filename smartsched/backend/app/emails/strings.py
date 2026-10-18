"""Shipped e-mail copy, Turkish first (W3-MAIL; design source docs/design/v3/emails.md §8, §9).

Keys live in the translation set ``email`` (``app.services.bookings_i18n.BASE_STRINGS`` merges this table), so the
existing override mechanism (``PUT /org/translations``, ``translations`` table) and ``GET /org/i18n`` cover them; the
admin e-mail template screen edits the same keys.

Parts per kind: ``subject``, ``preheader``, ``status`` (pill word), ``heading``, ``intro``, ``cta``, ``after`` (text
after the button), ``note``, ``why`` (footer reason). Variants: ``<kind>.<field>.<value>.<part>`` before
``<kind>.<part>``; enum labels ``<kind>.<field>.<value>``. The CRBS booking e-mails keep their former keys
(``booking_created.subject`` / ``.body``, ``room_owner.*``, ``booking_cancelled.*``): their intro key is the old body.

Placeholders never carry a Turkish suffix (``{org}`` alone, never ``{org}'e``): a name's vowel harmony is unknown.
"""

from __future__ import annotations

TR: dict[str, str] = {
    # --- layout (§5.9, §9) ------------------------------------------------------------------------
    "layout.footer.org": "{org} · SmartSched",
    "layout.footer.reason": "Bu e-postayı, SmartSched hesabınızla ilgili bir bildirim açık olduğu için aldınız.",
    "layout.footer.security": "Bu bir güvenlik e-postasıdır; bildirim tercihlerinden kapatılamaz.",
    "layout.footer.legal": "Bu e-posta yasal bir bildirimdir (KVKK); kapatılamaz.",
    "layout.footer.prefs": "Bildirim tercihleri",
    "layout.footer.kvkk": "KVKK Aydınlatma Metni",
    "layout.footer.sent_by": "SmartSched ile gönderildi",
    "layout.footer.no_reply": "Bu ileti otomatik gönderildi; yanıtlanmaz.",
    "layout.footer.reply_to": "Bu ileti otomatik gönderildi; yanıtlar {reply_to} adresine gider.",
    "layout.button_fallback": "Düğme çalışmıyorsa bu adresi tarayıcınıza yapıştırın:",
    "layout.reason": "Gerekçe",
    "layout.suggestions": "Aynı saatte boş derslikler",
    "layout.code": "Sıfırlama kodu",
    "layout.logo_alt": "SmartSched",
    "layout.article": "e-posta",
    "layout.details": "Ayrıntılar",
    "layout.more": "+{n} daha",
    "layout.row.requested_by": "Talep eden",
    "layout.row.room": "Derslik",
    "layout.row.date": "Tarih",
    "layout.row.period": "Ders saati",
    "layout.row.repeats": "Tekrar",
    "layout.row.dates": "Tarihler",
    "layout.row.note": "Not",
    "layout.row.conflict": "Çakışma",
    "layout.row.request_no": "Talep no",
    "layout.row.decided_by": "Karar veren",
    "layout.row.role": "Rol",
    "layout.row.invited": "Davet edilen adres",
    "layout.row.method": "Giriş yöntemi",
    "layout.row.valid_until": "Son geçerlilik",
    "layout.row.time": "Zaman",
    "layout.row.device": "Cihaz",
    "layout.row.location": "Yaklaşık konum",
    "layout.row.service": "Servis",
    "layout.row.started": "Başlangıç",
    "layout.row.count": "Tekrar sayısı",
    "layout.row.used": "Kullanılan",
    "layout.row.limit": "Sınır",
    "layout.row.request_kind": "Talep türü",
    "layout.row.due": "Son gün",
    # --- 8.1 password_reset -------------------------------------------------------------------------
    "password_reset.subject": "Parola sıfırlama kodunuz",
    "password_reset.preheader": "Kod {valid_hours} saat geçerli. Bu isteği siz yapmadıysanız bu e-postayı yok sayın.",
    "password_reset.heading": "Parolanızı sıfırlayın",
    "password_reset.intro": "Merhaba {name}, {org} SmartSched hesabınız için parola sıfırlama istendi.",
    "password_reset.cta": "Parolayı sıfırla",
    "password_reset.after": (
        "Kod {valid_hours} saat geçerlidir ve bir kez kullanılabilir. Düğme açılmazsa giriş sayfasında "
        '"Parolamı unuttum" adımına bu kodu yazın.'
    ),
    "password_reset.note": "Bu isteği siz yapmadınız mı? Bir şey yapmanız gerekmez; parolanız değişmez.",
    # --- 8.2 invitation -----------------------------------------------------------------------------
    "invitation.subject": "{inviter} sizi SmartSched'e davet etti",
    "invitation.heading": "SmartSched'e davet edildiniz",
    "invitation.intro": "{inviter}, sizi {org} ders programı ve derslik rezervasyonu sistemine davet etti.",
    "invitation.cta": "Daveti kabul et",
    "invitation.note": (
        "Bu daveti beklemiyorsanız e-postayı yok sayabilirsiniz; siz giriş yapmadan hesap etkinleşmez."
    ),
    "invitation.why": "Bu e-postayı, bir yönetici bu adresi davet ettiği için aldınız.",
    "invitation.provider.local": "Kullanıcı adı ve parola",
    "invitation.provider.microsoft": "Microsoft (iş veya okul hesabı)",
    "invitation.provider.google": "Google Workspace hesabı",
    "invitation.provider.oidc": "{provider_name} (kurumsal giriş)",
    "invitation.provider.saml": "{provider_name} (kurumsal tek oturum)",
    "invitation.provider.ldap": "Kurum kullanıcı adı ve parolası (LDAP)",
    "invitation.provider.local.preheader": "Parolanızı belirleyip katılın. Davet {expires} tarihine kadar geçerli.",
    "invitation.provider.microsoft.preheader": (
        "Microsoft iş veya okul hesabınızla katılın. Davet {expires} tarihine kadar geçerli."
    ),
    "invitation.provider.google.preheader": "Google Workspace hesabınızla katılın. Davet {expires} tarihine kadar "
    "geçerli.",
    "invitation.provider.oidc.preheader": "{provider_name} hesabınızla katılın. Davet {expires} tarihine kadar "
    "geçerli.",
    "invitation.provider.saml.preheader": "{provider_name} hesabınızla katılın. Davet {expires} tarihine kadar "
    "geçerli.",
    "invitation.provider.ldap.preheader": "Kurum hesabınızla katılın. Davet {expires} tarihine kadar geçerli.",
    "invitation.provider.local.after": "Açılan sayfada kullanıcı adınızı görür ve parolanızı belirlersiniz.",
    "invitation.provider.microsoft.after": (
        'Açılan sayfada "Microsoft ile giriş yap" düğmesine basın ve bu adresle giriş yapın. Hesabınız ilk '
        "girişte bağlanır."
    ),
    "invitation.provider.google.after": (
        'Açılan sayfada "Google ile oturum açın" düğmesine basın ve bu adresle giriş yapın.'
    ),
    "invitation.provider.oidc.after": 'Açılan sayfada "{provider_name} ile giriş yap" düğmesine basın.',
    "invitation.provider.saml.after": 'Açılan sayfada "{provider_name} ile giriş yap" düğmesine basın.',
    "invitation.provider.ldap.after": "Açılan sayfada kurum kullanıcı adınız ve parolanızla giriş yapın.",
    # --- 8.3 account_created -----------------------------------------------------------------------
    "account_created.subject": "SmartSched hesabınız hazır",
    "account_created.status": "Hesap açıldı",
    "account_created.heading": "Hoş geldiniz, {name}",
    "account_created.method.sso.preheader": "{provider} ile giriş yaptınız; rolünüz: {role}.",
    "account_created.method.local.preheader": "Bir yönetici hesabınızı açtı. Parolanızı {valid_hours} saat içinde "
    "belirleyin.",
    "account_created.method.sso.intro": (
        "{org} SmartSched hesabınız ilk girişinizde açıldı. Rolünüz: {role}. Rolünüzü yalnızca bir yönetici "
        "değiştirebilir."
    ),
    "account_created.intro": "{actor}, sizin için {org} SmartSched hesabı açtı. Kullanıcı adınız: {username}.",
    "account_created.method.sso.cta": "SmartSched'i aç",
    "account_created.cta": "Parolamı belirle",
    "account_created.note": "Sık kullanılanlar: Rezerve et, Rezervasyonlarım, Bildirim tercihleri (Profil).",
    "account_created.why": "Bu e-postayı, hesabınız açıldığı için aldınız.",
    "account_created.method.sso": "kurum hesabı",
    "account_created.method.local": "kullanıcı adı ve parola",
    # --- 8.4 new_device_sign_in --------------------------------------------------------------------
    "new_device_sign_in.subject": "Yeni bir cihazdan giriş yapıldı",
    "new_device_sign_in.preheader": "{when} · {device}. Siz değilseniz oturumu kapatın.",
    "new_device_sign_in.heading": "Hesabınıza yeni bir cihazdan giriş yapıldı",
    "new_device_sign_in.intro": (
        "Merhaba {name}, {org} SmartSched hesabınıza daha önce görmediğimiz bir cihazdan giriş yapıldı."
    ),
    "new_device_sign_in.cta": "Bu ben değilim",
    "new_device_sign_in.note": (
        "Siz iseniz bir şey yapmanız gerekmez. Değilseniz düğme açık oturumları gösterir; tümünü kapatıp parolanızı "
        "değiştirebilirsiniz."
    ),
    # --- 8.5 booking_created (CRBS keys kept) ---------------------------------------------------------
    "booking_created.subject": "Sizin adınıza rezervasyon yapıldı",
    "booking_created.body": "{actor} sizin adınıza {count} rezervasyon yaptı:\n{items}\n",
    "booking_created.status": "Rezerve edildi",
    "booking_created.heading": "{actor} sizin adınıza derslik ayırdı",
    "booking_created.cta": "Rezervasyonu görüntüle",
    "booking_created.why": 'Bu e-postayı, "Biri benim adıma rezervasyon yaptı" bildirimi açık olduğu için aldınız.',
    # --- 8.6 room_owner_booking ----------------------------------------------------------------------
    "room_owner.subject": "{room} için yeni rezervasyon",
    "room_owner.body": "{actor} sorumlu olduğunuz dersliği ayırttı{series}:\n{items}\n",
    "room_owner.series": " (seri #{series_id})",
    "room_owner_booking.status": "Rezerve edildi",
    "room_owner_booking.heading": "Sorumlu olduğunuz dersliğe rezervasyon yapıldı",
    "room_owner_booking.cta": "Dersliğin gününü aç",
    "room_owner_booking.why": "Bu e-postayı, derslik için sorumlu olarak kayıtlı olduğunuz için aldınız.",
    # --- 8.7 approval_submitted -----------------------------------------------------------------------
    "approval_submitted.subject": "Talebiniz alındı: {what}",
    "approval_submitted.preheader": "Onay bekliyor. Karar verildiğinde size haber vereceğiz.",
    "approval_submitted.status": "Onay bekliyor",
    "approval_submitted.heading": "Talebiniz onaya gönderildi",
    # approvals.py: a pending request holds its slot only when the rule says so (hold_minutes > 0)
    "approval_submitted.intro": (
        "Talebiniz onaycılara gönderildi: {what}. Karar verilene kadar aynı saat için başka talepler de olabilir; "
        "onaylanan talep dersliği alır."
    ),
    "approval_submitted.hold.held.intro": (
        "Talebiniz onaycılara gönderildi: {what}. Derslik {held_until} tarihine kadar sizin için tutulur."
    ),
    "approval_submitted.cta": "Talebimi görüntüle",
    "approval_submitted.note": "Vazgeçerseniz talebi Rezervasyonlarım'dan geri çekebilirsiniz.",
    "approval_submitted.why": 'Bu e-postayı, "Talebim alındı" bildirimi açık olduğu için aldınız.',
    # --- 8.8-8.12 approvals (same sentences as the bell: app/services/approvals.py TEXTS) -------------
    "approval_requested.subject": "Onay bekleyen oda talebi: {what}",
    "approval_requested.preheader": "{who} onay istiyor: {what}",
    "approval_requested.status": "Onay bekliyor",
    "approval_requested.heading": "Onayınızı bekleyen bir talep var",
    "approval_requested.intro": "{who} şu oda için onay istiyor: {what}.",
    "approval_requested.cta": "Talebi incele",
    "approval_requested.note": (
        "Karar uygulamada verilir; bu e-postadaki bağlantılar tek başına onaylamaz veya reddetmez."
    ),
    "approval_requested.why": "Bu e-postayı, bu derslik için onaycı olduğunuz için aldınız.",
    "approval_approved.subject": "Oda talebiniz onaylandı: {what}",
    "approval_approved.preheader": "Derslik bu saatlerde sizin adınıza ayrıldı.",
    "approval_approved.status": "Onaylandı",
    "approval_approved.heading": "Oda talebiniz onaylandı",
    "approval_approved.intro": "{who} talebinizi onayladı: {what}.",
    "approval_approved.cta": "Rezervasyonu görüntüle",
    "approval_approved.why": 'Bu e-postayı, "Talebim onaylandı" bildirimi açık olduğu için aldınız.',
    "approval_rejected.subject": "Oda talebiniz reddedildi: {what}",
    "approval_rejected.preheader": "Gerekçe: {reason}. Başka bir saat veya derslik deneyebilirsiniz.",
    "approval_rejected.status": "Reddedildi",
    "approval_rejected.heading": "Oda talebiniz reddedildi",
    "approval_rejected.intro": "{who} talebinizi reddetti: {what}.\nGerekçe: {reason}{alt}",
    "approval_rejected.cta": "Başka bir derslik bul",
    "approval_rejected.why": 'Bu e-postayı, "Talebim reddedildi" bildirimi açık olduğu için aldınız.',
    "approval_withdrawn.subject": "Oda talebi geri çekildi: {what}",
    "approval_withdrawn.preheader": "{who} talebini geri çekti; bir şey yapmanız gerekmez.",
    "approval_withdrawn.status": "Geri çekildi",
    "approval_withdrawn.heading": "Talep geri çekildi",
    "approval_withdrawn.intro": "{who} onayınızı bekleyen talebini geri çekti: {what}.",
    "approval_withdrawn.cta": "Onay kuyruğunu aç",
    "approval_withdrawn.to.requester.subject": "Oda talebinizi geri çektiniz: {what}",
    "approval_withdrawn.to.requester.preheader": "Derslik yeniden boş.",
    "approval_withdrawn.to.requester.heading": "Talebinizi geri çektiniz",
    "approval_withdrawn.to.requester.intro": "Talebiniz geri çekildi: {what}.",
    "approval_withdrawn.to.requester.cta": "Yeni talep oluştur",
    "approval_expired.subject": "Oda talebinizin süresi doldu: {what}",
    "approval_expired.preheader": "Talep, başlangıç saatinden önce onaylanmadı.",
    "approval_expired.status": "Süresi doldu",
    "approval_expired.heading": "Talebinizin süresi doldu",
    "approval_expired.intro": "Talebiniz başlangıçtan önce onaylanmadı: {what}.",
    "approval_expired.cta": "Yeniden rezerve et",
    # --- 8.13 booking_cancelled ----------------------------------------------------------------------
    "booking_cancelled.subject": "Rezervasyonunuz iptal edildi",
    "booking_cancelled.body": "{actor} {count} rezervasyonunuzu iptal etti:\n{items}{reason}\n",
    "booking_cancelled.reason": "\nGerekçe: {reason}",
    "booking_cancelled.reason.replaced_by_series": "Seri #{id} ile değiştirildi",
    "booking_cancelled.reason.undo_of": "Geri alma: #{id}",  # = the UI (cancel-reason.ts)
    "booking_cancelled.status": "İptal edildi",
    "booking_cancelled.heading": "Rezervasyonunuz iptal edildi",
    "booking_cancelled.preheader": "{actor} iptal etti.",
    "booking_cancelled.cause.replaced_by_series.preheader": "Yerine yeni bir seri geldi.",
    "booking_cancelled.cause.undo_of.preheader": "Bir işlem geri alındı.",
    "booking_cancelled.cta": "Başka bir derslik bul",
    "booking_cancelled.why": 'Bu e-postayı, "Rezervasyonum iptal edildi" bildirimi açık olduğu için aldınız.',
    # --- 8.14 booking_conflict_resolved ----------------------------------------------------------------
    "booking_conflict_resolved.subject": "Rezervasyonunuz yayınlanan programa göre değişti",
    "booking_conflict_resolved.preheader": "Yeni derslik ve saatler içeride.",
    "booking_conflict_resolved.status": "Değişti",
    "booking_conflict_resolved.heading": "Rezervasyonunuz değişti",
    "booking_conflict_resolved.intro": (
        "{term} programı yayınlandı ve rezervasyonunuz bir dersle çakışıyordu. Aşağıdaki değişiklik yapıldı:\n{items}"
    ),
    "booking_conflict_resolved.cta": "Rezervasyonlarımı aç",
    # --- 8.15 booking_reminder -------------------------------------------------------------------------
    "booking_reminder.subject": "Yarın: {room} · {period}",
    "booking_reminder.when.hour_before.subject": "{start} başlıyor: {room}",
    "booking_reminder.preheader": "{date} · {period}",
    "booking_reminder.heading": "Hatırlatma: yarın derslik ayırdınız",
    "booking_reminder.when.hour_before.heading": "Hatırlatma: {start} başlıyor",
    "booking_reminder.intro": "Merhaba {name}, rezervasyonunuz: {room}, {date} {period}.",
    "booking_reminder.cta": "Rezervasyonu görüntüle",
    "booking_reminder.note": "Gerekmiyorsa iptal edin; derslik başkasına açılır.",
    "booking_reminder.why": 'Bu e-postayı, "Rezervasyon hatırlatmaları" bildirimi açık olduğu için aldınız.',
    # --- 8.16-8.17 series ------------------------------------------------------------------------------
    "series_created.subject": "Yinelenen rezervasyon: {room} · {pattern}",
    "series_created.preheader": "{count} tarih · seri #{series_id}",
    "series_created.status": "Rezerve edildi",
    "series_created.heading": "Yinelenen rezervasyonunuz oluşturuldu",
    "series_created.intro": "{who} sizin için {room} dersliğinde {pattern} rezervasyon oluşturdu.\n{items}",
    "series_created.cta": "Seriyi görüntüle",
    "series_created.why": 'Bu e-postayı, "Yinelenen rezervasyonlarım" bildirimi açık olduğu için aldınız.',
    "series_changed.subject": "Seri #{series_id} değişti: {room}",
    "series_changed.preheader": "{change}",
    "series_changed.status": "Değişti",
    "series_changed.heading": "Yinelenen rezervasyonunuz değişti",
    "series_changed.intro": "{who} seri #{series_id} üzerinde değişiklik yaptı: {change}.\n{items}",
    "series_changed.cta": "Seriyi görüntüle",
    "series_changed.why": 'Bu e-postayı, "Yinelenen rezervasyonlarım" bildirimi açık olduğu için aldınız.',
    # --- 8.18 calendar_consent (personal; the organisation variant is scope.org) -----------------------
    "calendar_consent.subject": "{provider} takviminiz bağlandı",
    "calendar_consent.state.off.subject": "{provider} takviminizin bağlantısı kaldırıldı",
    "calendar_consent.preheader": "Rezervasyonlarınız bu takvime aktarılır.",
    "calendar_consent.state.off.preheader": "Aktarım durdu.",
    "calendar_consent.heading": "{provider} takviminiz bağlandı",
    "calendar_consent.state.off.heading": "{provider} takviminizin bağlantısı kaldırıldı",
    "calendar_consent.intro": (
        "Rezervasyonlarınızın tarih, saat, derslik ve not bilgileri {provider} takviminize aktarılır. "
        "{provider} sunucuları yurt dışındadır."
    ),
    "calendar_consent.state.off.intro": "Rezervasyonlarınız artık {provider} takviminize aktarılmıyor.",
    "calendar_consent.cta": "Bağlı takvimleri yönet",
    "calendar_consent.scope.org.subject": "Takvim eşitleme açıldı (KVKK onayı kaydedildi)",
    "calendar_consent.scope.org.heading": "Takvim eşitleme açıldı (KVKK onayı kaydedildi)",
    "calendar_consent.scope.org.preheader": "{actor}, {when}",
    "calendar_consent.scope.org.intro": (
        "{actor}, {when} tarihinde takvim eşitlemeyi açtı ve kurum adına KVKK onayını verdi. Rezervasyonların tarih, "
        "saat, derslik ve not bilgileri kullanıcıların bağladığı takvimlere aktarılabilir (sunucular yurt dışında)."
    ),
    "calendar_consent.scope.org.cta": "Entegrasyonları aç",
    "calendar_consent.provider.google": "Google",
    "calendar_consent.provider.microsoft": "Microsoft Outlook",
    "calendar_consent.state.on": "açıldı",
    "calendar_consent.state.off": "kapatıldı",
    # --- 8.19 kvkk_request ----------------------------------------------------------------------------
    "kvkk_request.subject": "KVKK talebiniz yanıtlandı",
    "kvkk_request.status.received.subject": "KVKK talebiniz alındı",
    "kvkk_request.status.refused.subject": "KVKK talebiniz hakkında yanıt",
    "kvkk_request.preheader": "{request_kind}: tamamlandı.",
    "kvkk_request.status.received.preheader": "Kanun, yanıt için 30 gün tanır.",
    "kvkk_request.status.refused.preheader": "Gerekçe içeride.",
    "kvkk_request.heading": "Talebiniz yanıtlandı",
    "kvkk_request.status.received.heading": "Talebinizi aldık",
    "kvkk_request.status.refused.heading": "Talebiniz karşılanamadı",
    "kvkk_request.intro": "{request_kind} talebiniz işlendi.\n{detail}",
    "kvkk_request.status.received.intro": "{request_kind} talebiniz kaydedildi. Kanun, yanıt için 30 gün tanır.",
    "kvkk_request.status.refused.intro": "{request_kind} talebiniz aşağıdaki gerekçeyle karşılanamadı.\nGerekçe: "
    "{detail}",
    "kvkk_request.cta": "Taleplerimi görüntüle",
    "kvkk_request.note": "Kanun gereği bazı kayıtlar takma adla saklanır (denetim kaydı).",
    "kvkk_request.status.refused.note": "İtiraz için Kişisel Verileri Koruma Kurulu'na başvurabilirsiniz.",
    "kvkk_request.status.received.note": "",
    "kvkk_request.request_kind.erase": "Silme",
    "kvkk_request.request_kind.rectify": "Düzeltme",
    "kvkk_request.request_kind.info": "Bilgi",
    "kvkk_request.request_kind.export": "Veri indirme",
    # --- 8.20 ai_usage_alert (suffix-free percent, §8.20) -------------------------------------------
    "ai_usage_alert.subject": "Yapay zekâ kullanım hakkınız: %{percent} kullanıldı",
    "ai_usage_alert.preheader": "{reset_date} tarihinde yenilenir.",
    "ai_usage_alert.status": "Uyarı",
    "ai_usage_alert.heading": "Kullanım hakkınız azalıyor",
    "ai_usage_alert.intro": (
        "Bu ayki yapay zekâ kullanım hakkınızın yüzde {percent} kadarı kullanıldı. {reset_date} tarihinde yenilenir."
    ),
    "ai_usage_alert.cta": "Kullanımımı gör",
    "ai_usage_alert.level.limit.subject": "Yapay zekâ kullanım sınırınıza ulaştınız",
    "ai_usage_alert.level.limit.preheader": "Ek kullanım için yöneticinize başvurun.",
    "ai_usage_alert.level.limit.heading": "Kullanım sınırına ulaşıldı",
    "ai_usage_alert.level.limit.intro": (
        "Bu ayki sınırınıza ulaştınız; yapay zekâ özellikleri {reset_date} tarihine kadar kapalı. Planlama ve "
        "rezervasyon çalışmaya devam eder."
    ),
    "ai_usage_alert.level.limit.cta": "Yöneticiye bildir",
    "ai_usage_alert.level.org_near.subject": "Kurum yapay zekâ bütçesi: %{percent} kullanıldı",
    "ai_usage_alert.level.org_near.preheader": "{used} / {limit} token · {reset_date} yenilenir",
    "ai_usage_alert.level.org_near.heading": "Kurum bütçesi azalıyor",
    "ai_usage_alert.level.org_near.intro": "{who}: kurumun bu ayki yapay zekâ bütçesinin yüzde {percent} kadarı "
    "kullanıldı.",
    "ai_usage_alert.level.org_near.cta": "Limitleri aç",
    "ai_usage_alert.level.org_limit.subject": "Kurum yapay zekâ bütçesi doldu",
    "ai_usage_alert.level.org_limit.preheader": "Yapay zekâ istekleri durdu.",
    "ai_usage_alert.level.org_limit.heading": "Bütçe doldu",
    "ai_usage_alert.level.org_limit.intro": "Yeni istekler {reset_date} tarihine kadar engelleniyor.",
    "ai_usage_alert.level.org_limit.cta": "Limitleri aç",
    # --- 8.21 ops_alert ------------------------------------------------------------------------------
    "ops_alert.subject": "[{severity}] {title}",
    "ops_alert.state.resolved.subject": "Çözüldü: {title}",
    "ops_alert.preheader": "{service} · {first_seen} itibarıyla · {count} kez",
    "ops_alert.state.resolved.preheader": "{duration} sürdü.",
    "ops_alert.status": "{severity}",
    "ops_alert.state.resolved.status": "Çözüldü",
    "ops_alert.heading": "{title}",
    "ops_alert.state.resolved.heading": "{title}: çözüldü",
    "ops_alert.intro": "{detail}",
    "ops_alert.state.resolved.intro": "Servis yeniden normal çalışıyor.",
    "ops_alert.cta": "Operasyon panelini aç",
    "ops_alert.state.resolved.cta": "Olay kaydını gör",
    "ops_alert.severity.critical": "Kritik",
    "ops_alert.severity.warning": "Uyarı",
    "ops_alert.severity.info": "Bilgi",
    "ops_alert.why": 'Bu e-postayı, "Operasyon uyarıları" bildirimi açık olduğu için aldınız.',
    # --- 8.22-8.24 existing kinds ----------------------------------------------------------------------
    "timetable_published.subject": "{term} programı yayınlandı: derslerinizde değişiklik var",
    "timetable_published.heading": "Derslerinizde değişiklik var",
    "timetable_published.intro": "{term} programı yayınlandı. Değişen dersleriniz:\n{items}",
    "timetable_published.cta": "Programımı aç",
    "preference_accepted.subject": "Ders tercihiniz kabul edildi: {course}",
    "preference_accepted.status": "Kabul edildi",
    "preference_accepted.heading": "Tercihiniz kabul edildi",
    "preference_accepted.intro": "{who} ders tercihinizi kabul etti: {course}, {what}.",
    "preference_accepted.cta": "Tercihlerimi aç",
    "preference_rejected.subject": "Ders tercihiniz kabul edilmedi: {course}",
    "preference_rejected.status": "Kabul edilmedi",
    "preference_rejected.heading": "Tercihiniz kabul edilmedi",
    "preference_rejected.intro": "{who} ders tercihinizi kabul etmedi: {course}, {what}.\nGerekçe: {reason}",
    "preference_rejected.cta": "Tercihlerimi aç",
    "smtp_test.subject": "SmartSched deneme iletisi",
    "smtp_test.preheader": "Bu iletiyi gördüyseniz bildirimler kullanıcılara ulaşır.",
    "smtp_test.heading": "E-posta ayarları çalışıyor",
    "smtp_test.intro": (
        "Bu bir deneme iletisidir. {host} üzerinden gönderildi. Bu iletiyi gördüyseniz bildirimler kullanıcılara "
        "ulaşır."
    ),
    "smtp_test.why": "Bu e-postayı, bir yönetici e-posta ayarlarını denediği için aldınız.",
    # --- RF-11 (2026-10-18): variants of the senders wired in app.services.mail_senders --------------------
    # a reminder more than a day ahead (the lead time is the admin's org setting bookings.reminder_lead_hours)
    "booking_reminder.when.later.subject": "{date}: {room} · {period}",
    "booking_reminder.when.later.heading": "Hatırlatma: {date} için derslik ayırdınız",
    "booking_reminder.when.hour_before.preheader": "{room} · {period}",
    "series_created.by.self.intro": "{room} dersliğinde {pattern} yinelenen rezervasyonunuz oluşturuldu.\n{items}",
    "series_created.by.self.heading": "Yinelenen rezervasyonunuz hazır",
    "series_changed.to.approver.heading": "Onayladığınız yinelenen rezervasyon değişti",
    "series_changed.to.approver.intro": (
        "{who}, onayladığınız seri #{series_id} üzerinde değişiklik yaptı: {change}.\n{items}"
    ),
    "series_changed.to.approver.why": "Bu e-postayı, bu seriyi siz onayladığınız için aldınız.",
    # the KVKK calendar_sync consent itself (Profil › Gizlilik), not a provider connection
    "calendar_consent.scope.consent_on.subject": "Takvim eşitleme izniniz kaydedildi",
    "calendar_consent.scope.consent_on.heading": "Takvim eşitleme izniniz kaydedildi",
    "calendar_consent.scope.consent_on.preheader": "İzninizi istediğiniz an geri çekebilirsiniz.",
    "calendar_consent.scope.consent_on.intro": (
        "Merhaba {name}, rezervasyonlarınızın tarih, saat, derslik ve not bilgilerinin bağladığınız Google ya da "
        "Microsoft takvimine aktarılmasına izin verdiniz. Bu hizmetlerin sunucuları yurt dışındadır."
    ),
    "calendar_consent.scope.consent_on.cta": "Gizlilik ayarlarını aç",
    "calendar_consent.scope.consent_on.note": (
        "İzninizi Profil › Gizlilik bölümünden istediğiniz an geri çekebilirsiniz."
    ),
    "calendar_consent.scope.consent_off.subject": "Takvim eşitleme izninizi geri çektiniz",
    "calendar_consent.scope.consent_off.heading": "Takvim eşitleme izninizi geri çektiniz",
    "calendar_consent.scope.consent_off.preheader": "Aktarım durdu.",
    "calendar_consent.scope.consent_off.intro": (
        "Merhaba {name}, rezervasyonlarınız artık Google ya da Microsoft takviminize aktarılmıyor. Takvim abonelik "
        "bağlantılarınız iptal edildi ve bağlı takvimleriniz kaldırıldı."
    ),
    "calendar_consent.scope.consent_off.cta": "Gizlilik ayarlarını aç",
    "calendar_consent.why": 'Bu e-postayı, "Takvim eşitleme iznim değişti" bildirimi açık olduğu için aldınız.',
    "new_device_sign_in.why": 'Bu e-postayı, "Hesabıma yeni bir cihazdan giriş yapıldı" bildirimi açık olduğu için '
    "aldınız.",
    # --- AU-B two-step sign-in, passkeys, admin resets (owner request 2026-10-18; security footer) ----------------
    "mfa_enabled.subject": "İki adımlı doğrulama açıldı",
    "mfa_enabled.preheader": "Girişte parolanızdan sonra bir kod da sorulacak.",
    "mfa_enabled.heading": "İki adımlı doğrulama açıldı",
    "mfa_enabled.intro": (
        "Merhaba {name}, {org} SmartSched hesabınızda iki adımlı doğrulama {when} tarihinde açıldı. Bundan sonra "
        "girişte parolanızdan sonra doğrulama uygulamanızdaki kod ya da geçiş anahtarınız istenecek."
    ),
    "mfa_enabled.cta": "Güvenlik ayarlarını aç",
    "mfa_enabled.after": (
        "Kurtarma kodlarınızı güvenli bir yerde saklayın; telefonunuzu kaybederseniz onlarla girersiniz."
    ),
    "mfa_enabled.note": "Bunu siz yapmadınız mı? Hemen parolanızı değiştirin ve yöneticinize haber verin.",
    "mfa_disabled.subject": "İki adımlı doğrulama kapatıldı",
    "mfa_disabled.preheader": "Girişte artık yalnızca parolanız soruluyor.",
    "mfa_disabled.heading": "İki adımlı doğrulama kapatıldı",
    "mfa_disabled.intro": (
        "Merhaba {name}, {org} SmartSched hesabınızda doğrulama uygulaması {when} tarihinde kapatıldı. Kurtarma "
        "kodlarınız ve güvenilir cihazlarınız da silindi."
    ),
    "mfa_disabled.cta": "Yeniden aç",
    "mfa_disabled.note": "Bunu siz yapmadınız mı? Hemen parolanızı değiştirin ve yöneticinize haber verin.",
    "mfa_reset_by_admin.subject": "İki adımlı doğrulamanız yönetici tarafından sıfırlandı",
    "mfa_reset_by_admin.preheader": "Girişte yalnızca parolanız sorulacak; doğrulamayı yeniden açın.",
    "mfa_reset_by_admin.heading": "İki adımlı doğrulamanız sıfırlandı",
    "mfa_reset_by_admin.intro": (
        "Merhaba {name}, {org} yöneticisi {actor}, {when} tarihinde hesabınızın iki adımlı doğrulamasını sıfırladı. "
        "Doğrulama uygulaması, kurtarma kodları ve güvenilir cihazlar kaldırıldı; tüm oturumlarınız kapatıldı."
    ),
    "mfa_reset_by_admin.cta": "Doğrulamayı yeniden aç",
    "mfa_reset_by_admin.after": (
        "Giriş yaptıktan sonra Profil › Güvenlik bölümünden doğrulama uygulamanızı yeniden ekleyin."
    ),
    "mfa_reset_by_admin.note": (
        "Böyle bir talepte bulunmadınız mı? Hemen yöneticinize ya da bilgi işlem birimine haber verin."
    ),
    "passkey_added.subject": "Hesabınıza yeni bir geçiş anahtarı eklendi",
    "passkey_added.preheader": "{device} adlı geçiş anahtarı eklendi.",
    "passkey_added.heading": "Yeni geçiş anahtarı eklendi",
    "passkey_added.intro": (
        "Merhaba {name}, {org} SmartSched hesabınıza {when} tarihinde {device} adlı bir geçiş anahtarı eklendi. Bu "
        "anahtarla parmak izi, yüz tanıma ya da cihaz PIN'i ile giriş yapılabilir."
    ),
    "passkey_added.cta": "Geçiş anahtarlarımı göster",
    "passkey_added.note": "Bu anahtarı siz eklemediniz mi? Güvenlik ayarlarından kaldırın ve parolanızı değiştirin.",
    "mfa_recovery_code_used.subject": "Bir kurtarma kodu kullanıldı",
    "mfa_recovery_code_used.preheader": "Kalan kurtarma kodu: {remaining}.",
    "mfa_recovery_code_used.heading": "Hesabınıza kurtarma koduyla girildi",
    "mfa_recovery_code_used.intro": (
        "Merhaba {name}, {org} SmartSched hesabınıza {when} tarihinde bir kurtarma koduyla giriş yapıldı. Kullanılan "
        "kod artık geçersiz; {remaining} kodunuz kaldı."
    ),
    "mfa_recovery_code_used.cta": "Yeni kurtarma kodları oluştur",
    "mfa_recovery_code_used.note": (
        "Bu giriş size ait değil mi? Hemen parolanızı değiştirin ve yöneticinize haber verin."
    ),
    "password_reset_link_by_admin.subject": "Parola sıfırlama bağlantınız",
    "password_reset_link_by_admin.preheader": "Bağlantı {valid_hours} saat geçerli ve bir kez kullanılabilir.",
    "password_reset_link_by_admin.heading": "Yeni parolanızı belirleyin",
    "password_reset_link_by_admin.intro": (
        "Merhaba {name}, {org} yöneticisi {actor}, SmartSched hesabınız için bir parola sıfırlama bağlantısı "
        "gönderdi. Yönetici parolanızı görmez ve seçemez; yeni parolayı siz belirlersiniz."
    ),
    "password_reset_link_by_admin.cta": "Yeni parola belirle",
    "password_reset_link_by_admin.after": (
        "Bağlantı {valid_hours} saat geçerlidir ve bir kez kullanılabilir. İki adımlı doğrulamanız açıksa girişte yine "
        "sorulur."
    ),
    "password_reset_link_by_admin.note": (
        "Böyle bir şey istemediniz mi? Bağlantıyı açmayın ve yöneticinize haber verin."
    ),
    "passkey_removed.subject": "Hesabınızdan bir geçiş anahtarı kaldırıldı",
    "passkey_removed.preheader": "{device} adlı geçiş anahtarı artık kullanılamaz.",
    "passkey_removed.heading": "Geçiş anahtarı kaldırıldı",
    "passkey_removed.intro": (
        "Merhaba {name}, {org} SmartSched hesabınızdan {when} tarihinde {device} adlı geçiş anahtarı kaldırıldı."
    ),
    "passkey_removed.cta": "Güvenlik ayarlarını aç",
    "passkey_removed.note": "Bunu siz yapmadınız mı? Hemen parolanızı değiştirin ve yöneticinize haber verin.",
    "recovery_codes_regenerated.subject": "Yeni kurtarma kodları oluşturuldu",
    "recovery_codes_regenerated.preheader": "Eski kurtarma kodlarınız artık geçersiz.",
    "recovery_codes_regenerated.heading": "Kurtarma kodlarınız yenilendi",
    "recovery_codes_regenerated.intro": (
        "Merhaba {name}, {org} SmartSched hesabınız için {when} tarihinde on yeni kurtarma kodu oluşturuldu. Eski "
        "kodlarınızın hiçbiri artık çalışmaz."
    ),
    "recovery_codes_regenerated.cta": "Güvenlik ayarlarını aç",
    "recovery_codes_regenerated.note": (
        "Bunu siz yapmadınız mı? Hemen parolanızı değiştirin ve yöneticinize haber verin."
    ),
    "mfa_required.subject": "İki adımlı doğrulama zorunlu oldu",
    "mfa_required.preheader": "{grace_days} gün içinde doğrulama uygulaması ya da geçiş anahtarı ekleyin.",
    "mfa_required.heading": "İki adımlı doğrulamayı açın",
    "mfa_required.intro": (
        "Merhaba {name}, {org} rolünüz için SmartSched girişinde iki adımlı doğrulamayı zorunlu tuttu. "
        "{grace_days} gün içinde bir doğrulama uygulaması ya da geçiş anahtarı ekleyin; bu süreden sonra girişte "
        "önce kurulum istenir."
    ),
    "mfa_required.cta": "Şimdi aç",
    "mfa_required.after": "Kurulum iki dakika sürer: Profil › Güvenlik › İki adımlı doğrulama.",
}

EN: dict[str, str] = {
    "layout.footer.org": "{org} · SmartSched",
    "layout.footer.reason": "You received this because a notification about your SmartSched account is on.",
    "layout.footer.security": "This is a security e-mail; it cannot be turned off in notification settings.",
    "layout.footer.legal": "This is a legal notice (KVKK); it cannot be turned off.",
    "layout.footer.prefs": "Notification settings",
    "layout.footer.kvkk": "Privacy notice (KVKK)",
    "layout.footer.sent_by": "Sent with SmartSched",
    "layout.footer.no_reply": "This message was sent automatically; replies are not read.",
    "layout.footer.reply_to": "This message was sent automatically; replies go to {reply_to}.",
    "layout.button_fallback": "If the button does not work, paste this address into your browser:",
    "layout.reason": "Reason",
    "layout.suggestions": "Rooms free at the same time",
    "layout.code": "Reset code",
    "layout.logo_alt": "SmartSched",
    "layout.article": "email",
    "layout.details": "Details",
    "layout.more": "+{n} more",
    "layout.row.requested_by": "Requested by",
    "layout.row.room": "Room",
    "layout.row.date": "Date",
    "layout.row.period": "Period",
    "layout.row.repeats": "Repeats",
    "layout.row.dates": "Dates",
    "layout.row.note": "Note",
    "layout.row.conflict": "Conflict",
    "layout.row.request_no": "Request no",
    "layout.row.decided_by": "Decided by",
    "layout.row.role": "Role",
    "layout.row.invited": "Invited address",
    "layout.row.method": "Sign-in method",
    "layout.row.valid_until": "Valid until",
    "layout.row.time": "Time",
    "layout.row.device": "Device",
    "layout.row.location": "Approximate location",
    "layout.row.service": "Service",
    "layout.row.started": "Started",
    "layout.row.count": "Count",
    "layout.row.used": "Used",
    "layout.row.limit": "Limit",
    "layout.row.request_kind": "Request type",
    "layout.row.due": "Due",
    "password_reset.subject": "Your password reset code",
    "password_reset.preheader": "The code is valid for {valid_hours} hours. If you did not ask for it, ignore this "
    "e-mail.",
    "password_reset.heading": "Reset your password",
    "password_reset.intro": "Hello {name}, a password reset was requested for your {org} SmartSched account.",
    "password_reset.cta": "Reset password",
    "password_reset.after": (
        "The code is valid for {valid_hours} hours and works once. If the button does not open, enter this code at "
        '"Forgot password" on the sign-in page.'
    ),
    "password_reset.note": "Didn't ask for this? You don't need to do anything; your password stays the same.",
    "invitation.subject": "{inviter} invited you to SmartSched",
    "invitation.heading": "You're invited to SmartSched",
    "invitation.intro": "{inviter} invited you to the {org} timetabling and room booking system.",
    "invitation.cta": "Accept invitation",
    "invitation.note": "If you weren't expecting this, you can ignore it; nothing is activated until you sign in.",
    "invitation.why": "You received this because an administrator invited this address.",
    "invitation.provider.local": "Username and password",
    "invitation.provider.microsoft": "Microsoft (work or school account)",
    "invitation.provider.google": "Google Workspace account",
    "invitation.provider.oidc": "{provider_name} (organisation sign-in)",
    "invitation.provider.saml": "{provider_name} (organisation single sign-on)",
    "invitation.provider.ldap": "Organisation username and password (LDAP)",
    "invitation.provider.local.preheader": "Set your password and join. Valid until {expires}.",
    "invitation.provider.microsoft.preheader": "Join with your Microsoft work or school account. Valid until "
    "{expires}.",
    "invitation.provider.google.preheader": "Join with your Google Workspace account. Valid until {expires}.",
    "invitation.provider.oidc.preheader": "Join with your {provider_name} account. Valid until {expires}.",
    "invitation.provider.saml.preheader": "Join with your {provider_name} account. Valid until {expires}.",
    "invitation.provider.ldap.preheader": "Join with your organisation account. Valid until {expires}.",
    "invitation.provider.local.after": "On the page that opens you see your username and set a password.",
    "invitation.provider.microsoft.after": (
        'On the page that opens choose "Sign in with Microsoft" and use this address. Your account is linked at the '
        "first sign-in."
    ),
    "invitation.provider.google.after": 'On the page that opens choose "Sign in with Google" and use this address.',
    "invitation.provider.oidc.after": 'On the page that opens choose "Sign in with {provider_name}".',
    "invitation.provider.saml.after": 'On the page that opens choose "Sign in with {provider_name}".',
    "invitation.provider.ldap.after": "On the page that opens sign in with your organisation username and password.",
    "account_created.subject": "Your SmartSched account is ready",
    "account_created.status": "Account created",
    "account_created.heading": "Welcome, {name}",
    "account_created.method.sso.preheader": "You signed in with {provider}; your role: {role}.",
    "account_created.method.local.preheader": "An administrator created your account. Set your password within "
    "{valid_hours} hours.",
    "account_created.method.sso.intro": (
        "Your {org} SmartSched account was created at your first sign-in. Your role: {role}. Only an administrator can "
        "change it."
    ),
    "account_created.intro": "{actor} created a {org} SmartSched account for you. Username: {username}.",
    "account_created.method.sso.cta": "Open SmartSched",
    "account_created.cta": "Set my password",
    "account_created.note": "Good to know: Reserve, My bookings, Notification settings (Profile).",
    "account_created.why": "You received this because your account was created.",
    "account_created.method.sso": "organisation account",
    "account_created.method.local": "username and password",
    "new_device_sign_in.subject": "New sign-in from another device",
    "new_device_sign_in.preheader": "{when} · {device}. If this wasn't you, sign it out.",
    "new_device_sign_in.heading": "Your account was used on a new device",
    "new_device_sign_in.intro": "Hello {name}, your {org} SmartSched account was signed in on a device we haven't "
    "seen before.",
    "new_device_sign_in.cta": "This wasn't me",
    "new_device_sign_in.note": (
        "If it was you, there is nothing to do. If not, the button shows your sessions; you can sign them all out and "
        "change your password."
    ),
    "booking_created.subject": "A booking was made for you",
    "booking_created.body": "{actor} made {count} booking(s) for you:\n{items}\n",
    "booking_created.status": "Booked",
    "booking_created.heading": "{actor} booked a room for you",
    "booking_created.cta": "View booking",
    "booking_created.why": 'You received this because "Someone booked a room for me" notifications are on.',
    "room_owner.subject": "New booking in {room}",
    "room_owner.body": "{actor} booked a room you own{series}:\n{items}\n",
    "room_owner.series": " (series #{series_id})",
    "room_owner_booking.status": "Booked",
    "room_owner_booking.heading": "New booking in a room you look after",
    "room_owner_booking.cta": "Open the room's day",
    "room_owner_booking.why": "You received this because you are listed as responsible for the room.",
    "approval_submitted.subject": "Your request was received: {what}",
    "approval_submitted.preheader": "Awaiting approval. We'll let you know when it's decided.",
    "approval_submitted.status": "Awaiting approval",
    "approval_submitted.heading": "Your request was sent for approval",
    "approval_submitted.intro": (
        "Your request was sent to the approvers: {what}. Until a decision, other requests for the same time may exist; "
        "the approved one gets the room."
    ),
    "approval_submitted.hold.held.intro": (
        "Your request was sent to the approvers: {what}. The room is held for you until {held_until}."
    ),
    "approval_submitted.cta": "View my request",
    "approval_submitted.note": "If you change your mind, withdraw it from My bookings.",
    "approval_submitted.why": 'You received this because "My request was received" notifications are on.',
    "approval_requested.subject": "Room request awaiting approval: {what}",
    "approval_requested.preheader": "{who} asks for approval: {what}",
    "approval_requested.status": "Awaiting approval",
    "approval_requested.heading": "A request is waiting for your approval",
    "approval_requested.intro": "{who} asks for approval: {what}.",
    "approval_requested.cta": "Review request",
    "approval_requested.note": "Decisions are made in the app; the links in this e-mail never approve or decline on "
    "their own.",
    "approval_requested.why": "You received this because you approve requests for this room.",
    "approval_approved.subject": "Your room request was approved: {what}",
    "approval_approved.preheader": "The room is booked for you at these times.",
    "approval_approved.status": "Approved",
    "approval_approved.heading": "Your room request was approved",
    "approval_approved.intro": "{who} approved your request: {what}.",
    "approval_approved.cta": "View booking",
    "approval_approved.why": 'You received this because "My request was approved" notifications are on.',
    "approval_rejected.subject": "Your room request was declined: {what}",
    "approval_rejected.preheader": "Reason: {reason}. You can try another time or room.",
    "approval_rejected.status": "Declined",
    "approval_rejected.heading": "Your room request was declined",
    "approval_rejected.intro": "{who} declined your request: {what}.\nReason: {reason}{alt}",
    "approval_rejected.cta": "Find another room",
    "approval_rejected.why": 'You received this because "My request was declined" notifications are on.',
    "approval_withdrawn.subject": "Room request withdrawn: {what}",
    "approval_withdrawn.preheader": "{who} withdrew it; nothing to do.",
    "approval_withdrawn.status": "Withdrawn",
    "approval_withdrawn.heading": "Request withdrawn",
    "approval_withdrawn.intro": "{who} withdrew the request awaiting your approval: {what}.",
    "approval_withdrawn.cta": "Open approval queue",
    "approval_withdrawn.to.requester.subject": "You withdrew your room request: {what}",
    "approval_withdrawn.to.requester.preheader": "The room is free again.",
    "approval_withdrawn.to.requester.heading": "You withdrew your request",
    "approval_withdrawn.to.requester.intro": "Your request was withdrawn: {what}.",
    "approval_withdrawn.to.requester.cta": "Make a new request",
    "approval_expired.subject": "Your room request expired: {what}",
    "approval_expired.preheader": "The request wasn't approved before it started.",
    "approval_expired.status": "Expired",
    "approval_expired.heading": "Your request expired",
    "approval_expired.intro": "Your request was not approved before it started: {what}.",
    "approval_expired.cta": "Book again",
    "booking_cancelled.subject": "Your booking was cancelled",
    "booking_cancelled.body": "{actor} cancelled {count} of your bookings:\n{items}{reason}\n",
    "booking_cancelled.reason": "\nReason: {reason}",
    "booking_cancelled.reason.replaced_by_series": "Replaced by series #{id}",
    "booking_cancelled.reason.undo_of": "Undo of #{id}",
    "booking_cancelled.status": "Cancelled",
    "booking_cancelled.heading": "Your booking was cancelled",
    "booking_cancelled.preheader": "{actor} cancelled it.",
    "booking_cancelled.cause.replaced_by_series.preheader": "Replaced by a new series.",
    "booking_cancelled.cause.undo_of.preheader": "An action was undone.",
    "booking_cancelled.cta": "Find another room",
    "booking_cancelled.why": 'You received this because "My booking was cancelled" notifications are on.',
    "booking_conflict_resolved.subject": "Your booking changed to fit the published timetable",
    "booking_conflict_resolved.preheader": "New rooms and times inside.",
    "booking_conflict_resolved.status": "Changed",
    "booking_conflict_resolved.heading": "Your booking changed",
    "booking_conflict_resolved.intro": (
        "The {term} timetable was published and your booking clashed with a class. This change was made:\n{items}"
    ),
    "booking_conflict_resolved.cta": "Open my bookings",
    "booking_reminder.subject": "Tomorrow: {room} · {period}",
    "booking_reminder.when.hour_before.subject": "Starts at {start}: {room}",
    "booking_reminder.preheader": "{date} · {period}",
    "booking_reminder.heading": "Reminder: you have a room tomorrow",
    "booking_reminder.when.hour_before.heading": "Reminder: starts at {start}",
    "booking_reminder.intro": "Hello {name}, your booking: {room}, {date} {period}.",
    "booking_reminder.cta": "View booking",
    "booking_reminder.note": "If you no longer need it, cancel it so others can book the room.",
    "booking_reminder.why": 'You received this because "Booking reminders" notifications are on.',
    "series_created.subject": "Recurring booking: {room} · {pattern}",
    "series_created.preheader": "{count} dates · series #{series_id}",
    "series_created.status": "Booked",
    "series_created.heading": "Your recurring booking was created",
    "series_created.intro": "{who} created a recurring booking for you in {room}, {pattern}.\n{items}",
    "series_created.cta": "View series",
    "series_created.why": 'You received this because "My recurring bookings" notifications are on.',
    "series_changed.subject": "Series #{series_id} changed: {room}",
    "series_changed.preheader": "{change}",
    "series_changed.status": "Changed",
    "series_changed.heading": "Your recurring booking changed",
    "series_changed.intro": "{who} changed series #{series_id}: {change}.\n{items}",
    "series_changed.cta": "View series",
    "series_changed.why": 'You received this because "My recurring bookings" notifications are on.',
    "calendar_consent.subject": "Your {provider} calendar is connected",
    "calendar_consent.state.off.subject": "Your {provider} calendar was disconnected",
    "calendar_consent.preheader": "Your bookings are copied to it.",
    "calendar_consent.state.off.preheader": "Copying stopped.",
    "calendar_consent.heading": "Your {provider} calendar is connected",
    "calendar_consent.state.off.heading": "Your {provider} calendar was disconnected",
    "calendar_consent.intro": (
        "The date, time, room and note of your bookings are copied to your {provider} calendar. Its servers are "
        "outside Türkiye."
    ),
    "calendar_consent.state.off.intro": "Your bookings are no longer copied to your {provider} calendar.",
    "calendar_consent.cta": "Manage connected calendars",
    "calendar_consent.scope.org.subject": "Calendar sync turned on (KVKK consent recorded)",
    "calendar_consent.scope.org.heading": "Calendar sync turned on (KVKK consent recorded)",
    "calendar_consent.scope.org.preheader": "{actor}, {when}",
    "calendar_consent.scope.org.intro": (
        "{actor} turned calendar sync on at {when} and gave KVKK consent for the organisation. Booking date, time, "
        "room "
        "and note can be copied to calendars users connect (servers abroad)."
    ),
    "calendar_consent.scope.org.cta": "Open integrations",
    "calendar_consent.provider.google": "Google",
    "calendar_consent.provider.microsoft": "Microsoft Outlook",
    "calendar_consent.state.on": "on",
    "calendar_consent.state.off": "off",
    "kvkk_request.subject": "Your KVKK request was answered",
    "kvkk_request.status.received.subject": "We received your KVKK request",
    "kvkk_request.status.refused.subject": "About your KVKK request",
    "kvkk_request.preheader": "{request_kind}: done.",
    "kvkk_request.status.received.preheader": "The law allows 30 days for an answer.",
    "kvkk_request.status.refused.preheader": "The reason is inside.",
    "kvkk_request.heading": "Your request was answered",
    "kvkk_request.status.received.heading": "We received your request",
    "kvkk_request.status.refused.heading": "Your request could not be fulfilled",
    "kvkk_request.intro": "Your {request_kind} request was processed.\n{detail}",
    "kvkk_request.status.received.intro": "Your {request_kind} request was recorded. The law allows 30 days for an "
    "answer.",
    "kvkk_request.status.refused.intro": "Your {request_kind} request could not be fulfilled for the reason "
    "below.\nReason: {detail}",
    "kvkk_request.cta": "View my requests",
    "kvkk_request.note": "By law some records are kept pseudonymised (audit log).",
    "kvkk_request.status.refused.note": "You can appeal to the Turkish Personal Data Protection Board (KVKK Kurulu).",
    "kvkk_request.status.received.note": "",
    "kvkk_request.request_kind.erase": "erasure",
    "kvkk_request.request_kind.rectify": "rectification",
    "kvkk_request.request_kind.info": "information",
    "kvkk_request.request_kind.export": "data export",
    "ai_usage_alert.subject": "You have used {percent}% of your AI allowance",
    "ai_usage_alert.preheader": "It resets on {reset_date}.",
    "ai_usage_alert.status": "Warning",
    "ai_usage_alert.heading": "Your allowance is running low",
    "ai_usage_alert.intro": "You have used {percent}% of this month's AI allowance. It resets on {reset_date}.",
    "ai_usage_alert.cta": "View my usage",
    "ai_usage_alert.level.limit.subject": "You have reached your AI limit",
    "ai_usage_alert.level.limit.preheader": "Ask your administrator for more.",
    "ai_usage_alert.level.limit.heading": "Usage limit reached",
    "ai_usage_alert.level.limit.intro": (
        "You have reached this month's limit; AI features are paused until {reset_date}. Planning and booking keep "
        "working."
    ),
    "ai_usage_alert.level.limit.cta": "Notify an administrator",
    "ai_usage_alert.level.org_near.subject": "{percent}% of the organisation's AI budget is used",
    "ai_usage_alert.level.org_near.preheader": "{used} / {limit} tokens · resets {reset_date}",
    "ai_usage_alert.level.org_near.heading": "The organisation's budget is running low",
    "ai_usage_alert.level.org_near.intro": "{who}: {percent}% of the organisation's AI budget for this month is used.",
    "ai_usage_alert.level.org_near.cta": "Open limits",
    "ai_usage_alert.level.org_limit.subject": "The organisation's AI budget is used up",
    "ai_usage_alert.level.org_limit.preheader": "AI requests stopped.",
    "ai_usage_alert.level.org_limit.heading": "Budget used up",
    "ai_usage_alert.level.org_limit.intro": "New requests are blocked until {reset_date}.",
    "ai_usage_alert.level.org_limit.cta": "Open limits",
    "ops_alert.subject": "[{severity}] {title}",
    "ops_alert.state.resolved.subject": "Resolved: {title}",
    "ops_alert.preheader": "{service} · since {first_seen} · {count} times",
    "ops_alert.state.resolved.preheader": "Lasted {duration}.",
    "ops_alert.status": "{severity}",
    "ops_alert.state.resolved.status": "Resolved",
    "ops_alert.heading": "{title}",
    "ops_alert.state.resolved.heading": "{title}: resolved",
    "ops_alert.intro": "{detail}",
    "ops_alert.state.resolved.intro": "The service is back to normal.",
    "ops_alert.cta": "Open operations panel",
    "ops_alert.state.resolved.cta": "View incident log",
    "ops_alert.severity.critical": "Critical",
    "ops_alert.severity.warning": "Warning",
    "ops_alert.severity.info": "Info",
    "ops_alert.why": 'You received this because "Operations alerts" notifications are on.',
    "timetable_published.subject": "The {term} timetable is published: your classes changed",
    "timetable_published.heading": "Your classes changed",
    "timetable_published.intro": "The {term} timetable was published. Your changed classes:\n{items}",
    "timetable_published.cta": "Open my timetable",
    "preference_accepted.subject": "Your class preference was accepted: {course}",
    "preference_accepted.status": "Accepted",
    "preference_accepted.heading": "Preference accepted",
    "preference_accepted.intro": "{who} accepted your class preference: {course}, {what}.",
    "preference_accepted.cta": "Open my preferences",
    "preference_rejected.subject": "Your class preference was declined: {course}",
    "preference_rejected.status": "Declined",
    "preference_rejected.heading": "Preference declined",
    "preference_rejected.intro": "{who} declined your class preference: {course}, {what}.\nReason: {reason}",
    "preference_rejected.cta": "Open my preferences",
    "smtp_test.subject": "SmartSched test message",
    "smtp_test.preheader": "If you can read this, notifications will reach your users.",
    "smtp_test.heading": "E-mail settings work",
    "smtp_test.intro": "This is a test message. Sent through {host}. If you can read this, notifications will reach "
    "your users.",
    "smtp_test.why": "You received this because an administrator tested the e-mail settings.",
    # --- RF-11 (2026-10-18) -----------------------------------------------------------------------------
    "booking_reminder.when.later.subject": "{date}: {room} · {period}",
    "booking_reminder.when.later.heading": "Reminder: you have a room on {date}",
    "booking_reminder.when.hour_before.preheader": "{room} · {period}",
    "series_created.by.self.intro": "Your recurring booking in {room}, {pattern}, was created.\n{items}",
    "series_created.by.self.heading": "Your recurring booking is ready",
    "series_changed.to.approver.heading": "A recurring booking you approved changed",
    "series_changed.to.approver.intro": "{who} changed series #{series_id}, which you approved: {change}.\n{items}",
    "series_changed.to.approver.why": "You received this because you approved this series.",
    "calendar_consent.scope.consent_on.subject": "Your calendar sync consent was recorded",
    "calendar_consent.scope.consent_on.heading": "Your calendar sync consent was recorded",
    "calendar_consent.scope.consent_on.preheader": "You can withdraw it at any time.",
    "calendar_consent.scope.consent_on.intro": (
        "Hello {name}, you allowed the date, time, room and note of your bookings to be copied to the Google or "
        "Microsoft calendar you connect. These services' servers are outside Türkiye."
    ),
    "calendar_consent.scope.consent_on.cta": "Open privacy settings",
    "calendar_consent.scope.consent_on.note": "You can withdraw it at any time under Profile › Privacy.",
    "calendar_consent.scope.consent_off.subject": "You withdrew your calendar sync consent",
    "calendar_consent.scope.consent_off.heading": "You withdrew your calendar sync consent",
    "calendar_consent.scope.consent_off.preheader": "Copying stopped.",
    "calendar_consent.scope.consent_off.intro": (
        "Hello {name}, your bookings are no longer copied to your Google or Microsoft calendar. Your calendar "
        "subscription links were revoked and your connected calendars removed."
    ),
    "calendar_consent.scope.consent_off.cta": "Open privacy settings",
    "calendar_consent.why": 'You received this because "My calendar sync consent changed" notifications are on.',
    "new_device_sign_in.why": 'You received this because "My account was signed in on a new device" notifications '
    "are on.",
    # --- AU-B two-step sign-in, passkeys, admin resets ---------------------------------------------------------------
    "mfa_enabled.subject": "Two-step verification is on",
    "mfa_enabled.preheader": "Signing in will ask for a code after your password.",
    "mfa_enabled.heading": "Two-step verification is on",
    "mfa_enabled.intro": (
        "Hello {name}, two-step verification was turned on for your {org} SmartSched account on {when}. From now on, "
        "signing in asks for the code from your authenticator app or your passkey after your password."
    ),
    "mfa_enabled.cta": "Open security settings",
    "mfa_enabled.after": "Keep your recovery codes somewhere safe; they get you in if you lose your phone.",
    "mfa_enabled.note": "Wasn't this you? Change your password now and tell your administrator.",
    "mfa_disabled.subject": "Two-step verification is off",
    "mfa_disabled.preheader": "Signing in now asks only for your password.",
    "mfa_disabled.heading": "Two-step verification is off",
    "mfa_disabled.intro": (
        "Hello {name}, the authenticator app was turned off for your {org} SmartSched account on {when}. Your "
        "recovery codes and trusted devices were removed too."
    ),
    "mfa_disabled.cta": "Turn it on again",
    "mfa_disabled.note": "Wasn't this you? Change your password now and tell your administrator.",
    "mfa_reset_by_admin.subject": "An administrator reset your two-step verification",
    "mfa_reset_by_admin.preheader": "Signing in asks only for your password; set up verification again.",
    "mfa_reset_by_admin.heading": "Your two-step verification was reset",
    "mfa_reset_by_admin.intro": (
        "Hello {name}, {actor}, an administrator of {org}, reset two-step verification for your account on {when}. "
        "The authenticator app, the recovery codes and the trusted devices were removed and you were signed out "
        "everywhere."
    ),
    "mfa_reset_by_admin.cta": "Set up verification again",
    "mfa_reset_by_admin.after": "After signing in, add your authenticator app again under Profile › Security.",
    "mfa_reset_by_admin.note": "Didn't ask for this? Tell your administrator or the IT department right away.",
    "passkey_added.subject": "A new passkey was added to your account",
    "passkey_added.preheader": "The passkey {device} was added.",
    "passkey_added.heading": "New passkey added",
    "passkey_added.intro": (
        "Hello {name}, a passkey named {device} was added to your {org} SmartSched account on {when}. It can sign "
        "in with a fingerprint, face recognition or the device PIN."
    ),
    "passkey_added.cta": "Show my passkeys",
    "passkey_added.note": "Didn't add it? Remove it in the security settings and change your password.",
    "mfa_recovery_code_used.subject": "A recovery code was used",
    "mfa_recovery_code_used.preheader": "Recovery codes left: {remaining}.",
    "mfa_recovery_code_used.heading": "Someone signed in with a recovery code",
    "mfa_recovery_code_used.intro": (
        "Hello {name}, your {org} SmartSched account was signed in with a recovery code on {when}. That code no "
        "longer works; you have {remaining} left."
    ),
    "mfa_recovery_code_used.cta": "Create new recovery codes",
    "mfa_recovery_code_used.note": "Wasn't this you? Change your password now and tell your administrator.",
    "password_reset_link_by_admin.subject": "Your password reset link",
    "password_reset_link_by_admin.preheader": "The link is valid for {valid_hours} hours and works once.",
    "password_reset_link_by_admin.heading": "Choose a new password",
    "password_reset_link_by_admin.intro": (
        "Hello {name}, {actor}, an administrator of {org}, sent you a password reset link for your SmartSched "
        "account. Administrators never see or choose your password; you set the new one."
    ),
    "password_reset_link_by_admin.cta": "Set a new password",
    "password_reset_link_by_admin.after": (
        "The link is valid for {valid_hours} hours and works once. If two-step verification is on, signing in still "
        "asks for it."
    ),
    "password_reset_link_by_admin.note": "Didn't expect this? Don't open the link and tell your administrator.",
    "passkey_removed.subject": "A passkey was removed from your account",
    "passkey_removed.preheader": "The passkey {device} no longer works.",
    "passkey_removed.heading": "Passkey removed",
    "passkey_removed.intro": (
        "Hello {name}, the passkey {device} was removed from your {org} SmartSched account on {when}."
    ),
    "passkey_removed.cta": "Open security settings",
    "passkey_removed.note": "Wasn't this you? Change your password now and tell your administrator.",
    "recovery_codes_regenerated.subject": "New recovery codes were created",
    "recovery_codes_regenerated.preheader": "Your old recovery codes no longer work.",
    "recovery_codes_regenerated.heading": "Your recovery codes were renewed",
    "recovery_codes_regenerated.intro": (
        "Hello {name}, ten new recovery codes were created for your {org} SmartSched account on {when}. None of the "
        "old codes works any more."
    ),
    "recovery_codes_regenerated.cta": "Open security settings",
    "recovery_codes_regenerated.note": "Wasn't this you? Change your password now and tell your administrator.",
    "mfa_required.subject": "Two-step verification is now required",
    "mfa_required.preheader": "Add an authenticator app or a passkey within {grace_days} days.",
    "mfa_required.heading": "Turn on two-step verification",
    "mfa_required.intro": (
        "Hello {name}, {org} now requires two-step verification for your role when signing in to SmartSched. Add an "
        "authenticator app or a passkey within {grace_days} days; after that, signing in asks you to set it up first."
    ),
    "mfa_required.cta": "Turn it on now",
    "mfa_required.after": "It takes two minutes: Profile › Security › Two-step verification.",
}

SHIPPED: dict[str, dict[str, str]] = {"tr": TR, "en": EN}


def shipped(locale: str) -> dict[str, str]:
    """The shipped strings of ``locale`` (``tr`` / ``en``; anything else reads English per key)."""
    out = dict(EN)
    if locale == "tr":
        out.update(TR)
    return out
