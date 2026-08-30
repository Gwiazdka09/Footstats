# Mejl do API-Football — konto zawieszone

**Status:** ✅ **WYSŁANE 2026-08-30, 20:28** przez użytkownika, z konta
`Gwiazdka09 <jakubgwiazdowski12@gmail.com>` na `support@api-sports.io`.
Czekamy na odpowiedź.
**Data szkicu:** 2026-08-30

## Dane konta (z panelu, 30.08)

- **Login:** `Gwiazdka09`
- **E-mail konta:** `jakubgwiazdowski12@gmail.com`
- **Powiadomienie w panelu:** „Your account is Suspended" (*Recent Notifications*)

Uwaga: to **inny adres** niż Twój główny (`gwiazdowskijakub47@gmail.com`).
Wyślij z `jakubgwiazdowski12@gmail.com` — z innego adresu support nie połączy
zgłoszenia z kontem, a to najczęstszy powód, dla którego takie sprawy stoją.

## Zanim wyślesz — sprawdź dwie rzeczy

1. **Plan** — napisałem „free plan (100 requests/day)". Jeśli masz inny, popraw.
2. **Data zawieszenia** — pierwszy ślad w naszych logach to **01.08.2026**.
   Jeśli pamiętasz coś wcześniejszego, dopisz.

Kanał: formularz kontaktowy na `dashboard.api-football.com` (zakładka *Support*)
albo `support@api-sports.io`. Formularz zwykle działa szybciej, bo automatycznie
dołącza identyfikator konta.

## Fakty, które mamy zmierzone (do ewentualnych dopytań)

- API odpowiada **HTTP 200** z ciałem `{"errors":{"access":"Your account is
  suspended"}}` — czyli to zawieszenie konta, nie przekroczenie limitu
  (limit zwraca inny komunikat).
- Widoczne w logach produkcyjnych codziennie od 01.08.2026 do dziś.
- Skutek u nas: `/fixtures`, `/fixtures/lineups` i `/odds` przestały zwracać dane.
- Zero powiadomienia mejlem. Komunikat „Your account is Suspended" widnieje
  wyłącznie w panelu, w sekcji *Recent Notifications*, i **nie podaje powodu**.

---

## Treść (EN)

**Temat:** Account suspended since 1 August 2026 — request for reason and reinstatement

Hello,

My API-Football account has been returning a suspension error since 1 August 2026
and I would like to understand why, and what I need to do to have it restored.

**What I observe**

Every request returns HTTP 200 with this body:

```json
{"errors": {"access": "Your account is suspended"}}
```

This has been consistent, every day, since 1 August 2026. It affects all
endpoints I use: `/fixtures`, `/fixtures/lineups` and `/odds`.

The only indication anywhere is a single line in the dashboard under *Recent
Notifications*: "Your account is Suspended". It gives no reason, and I received
no email about it, so I have no information about the cause.

**How I use the API**

The account is used by a personal, non-commercial football statistics project
that I run alone. It is a hobby project: there are no paying users, no
advertising and no resale or redistribution of your data. The data is used to
compute match probabilities that are displayed only to me and a small number of
private users.

I am on the free plan and my usage stays within the 100 requests/day limit — the
application has its own internal counter and a 24-hour disk cache specifically to
avoid exceeding it. Typical usage is well below the limit.

**What I am asking**

1. What was the reason for the suspension?
2. What do I need to change so the account can be reinstated?

If something in my usage broke your terms of service, I will gladly correct it —
I would simply like to know what it was. If the suspension was applied in error,
I would be grateful if you could restore access.

Account username: Gwiazdka09
Account e-mail: jakubgwiazdowski12@gmail.com

Thank you for your time,
Jakub

---

## Treść (PL — gdyby wolał ktoś polskojęzyczny kanał)

**Temat:** Konto zawieszone od 1 sierpnia 2026 — prośba o powód i przywrócenie

Dzień dobry,

od 1 sierpnia 2026 moje konto API-Football zwraca komunikat o zawieszeniu.
Chciałbym poznać powód i dowiedzieć się, co muszę zrobić, żeby odzyskać dostęp.

Każde zapytanie kończy się odpowiedzią HTTP 200 z treścią:

```json
{"errors": {"access": "Your account is suspended"}}
```

Dzieje się tak codziennie od 1 sierpnia, na wszystkich używanych przeze mnie
punktach końcowych: `/fixtures`, `/fixtures/lineups` i `/odds`. Jedyny ślad to
linijka w panelu, w sekcji *Recent Notifications*: „Your account is Suspended" —
bez podanego powodu. Nie dostałem żadnej wiadomości e-mail.

Konto obsługuje prywatny, niekomercyjny projekt statystyk piłkarskich, który
prowadzę sam. Nie ma płacących użytkowników, reklam ani odsprzedaży Waszych
danych. Korzystam z planu darmowego i mieszczę się w limicie 100 zapytań na
dobę — aplikacja ma własny licznik zużycia i 24-godzinny cache na dysku właśnie
po to, żeby limitu nie przekraczać.

Proszę o informację:

1. jaki był powód zawieszenia,
2. co mam zmienić, żeby konto zostało przywrócone.

Jeśli coś w moim sposobie korzystania naruszyło regulamin, chętnie to poprawię —
zależy mi wyłącznie na tym, żeby wiedzieć co. Jeśli zawieszenie nastąpiło przez
pomyłkę, będę wdzięczny za przywrócenie dostępu.

Login konta: Gwiazdka09
Adres e-mail konta: jakubgwiazdowski12@gmail.com

Z poważaniem,
Jakub

---

## Czego świadomie NIE napisałem

- **Nie deklarowałem, że na pewno nie złamaliśmy regulaminu.** Nie wiemy tego —
  nie znamy powodu zawieszenia. Zapewnianie o niewinności bez wiedzy osłabia
  zgłoszenie, jeśli okaże się nieprawdą.
- **Nie prosiłem o rekompensatę ani nie groziłem odejściem.** Konto jest darmowe;
  jedyne, co realnie działa, to konkretne pytanie o przyczynę.
- **Nie podałem nazwy projektu ani adresu serwisu.** Dopisz, jeśli chcesz —
  ale zwróć uwagę, że wskazanie publicznego serwisu z prognozami może zostać
  odczytane jako użycie komercyjne, nawet gdy nic na nim nie zarabiasz.
