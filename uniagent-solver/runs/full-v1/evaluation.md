| Falltyp | Accuracy | richtig/Fälle |
|---|---|---|
| auslagenerstattung | 0.88 | 7/8 |
| beschaffungsantrag | 1.00 | 8/8 |
| dienstreiseantrag | 0.60 | 3/5 |
| **gesamt** | **0.86** | 18/21 |

Sekunden/Fall: 38.7, Tokens/Fall: 6856

FALSCH dienstreiseantrag-02: vorhergesagt abgelehnt, Gold angenommen
  Gold: Vollstaendiger, rund zehn Wochen vor Reisebeginn eingereichter Antrag. Das dienstliche Interesse ist durch die Annahmebestaetigung des Peer-Review-Beitrags belegt, die Praesentationspflicht ergibt sich aus derselben Mail. Kosten sind plausibel und durch das genannte Drittmittelprojekt gedeckt, der Uebernachtungssatz von 75 EUR liegt innerhalb der Hoechstgrenze, der Preisvergleich Bahn/Flug wurde durchgefuehrt, die A1-Bescheinigung mit ausreichendem Vorlauf beantragt und das optionale Conference Dinner nicht mitbeantragt. Keine offenen Angaben oder Widersprueche.
  System: Der Antrag weist keine Genehmigung auf – im Feld "Genehmigt von" steht lediglich "---". Nach Regel TRIP_SUBMITTED_BEFORE_START dürfen Reisekosten erstattet werden, wenn die Reise vorher angeordnet oder genehmigt ist; ohne Genehmigung ist keine Abrechnung möglich. Alle anderen Kriterien (Reisedaten, Kosten, A1‑Bescheinigung, Preisvergleich, Drittmittelangabe) sind erfüllt, jedoch ist die fehlende Genehmigung der ausschlaggebende Mangel.

FALSCH dienstreiseantrag-04: vorhergesagt abgelehnt, Gold angenommen
  Gold: Das erhebliche dienstliche Interesse ist durch die Einladung als Keynote-Speaker belegt. Der private Anschlussaufenthalt umfasst mit 6 Tagen mehr als die zulaessigen 5 Arbeitstage, wird aber korrekt behandelt: beantragt sind ausschliesslich die dienstlich veranlassten Kosten (Hinflug, Rueckflug zum Vergleichstarif des dienstlichen Rueckreisetags, 3 Naechte zum Konferenztarif, Konferenzgebuehr, Transfer). Die 6 privaten Naechte (480 EUR) und der Flugmehrpreis (40 EUR) werden selbst getragen; der Preisvergleich des Reisebueros und die getrennten Hotelbuchungen belegen, dass der Universitaet keine Mehrkosten entstehen. Rechtzeitig eingereicht, A1 beantragt.
  System: Der Antrag weist keine Genehmigung auf – im Feld "Genehmigt von" steht lediglich "---". Nach TRIP_SUBMITTED_BEFORE_START dürfen Reisekosten nur erstattet werden, wenn die Reise vorher angeordnet oder genehmigt ist; ohne Genehmigung ist die Abrechnung nicht möglich. Alle anderen Regelungen sind erfüllt, jedoch ist die fehlende Genehmigung ein konkreter, wesentlicher Mangel.

FALSCH auslagenerstattung-01: vorhergesagt abgelehnt, Gold angenommen
  Gold: Die englischsprachige Marktplatzrechnung FPM-NL-27-004471908 vom 12.02.2027 weist ein Fachbuch zu Methoden der stochastischen Optimalsteuerung über insgesamt 94,40 € aus, verkauft von einem Händler in Utrecht. Rechnungsempfänger ist der zentrale Rechnungseingang der Universität Wernstadt, geliefert wurde an den Lehrstuhl für Stochastische Systeme; der dienstliche Bezug ist damit belegt. Die Rechnung ist ein Originalbeleg mit genanntem Artikel, wie es der Abschnitt Kostenerstattung der Uni-Kassel-Seite „Finanzbuchhaltung und Steuern“ verlangt, und die Beträge (7 % USt auf Buch und Versand) gehen auf. Die Erstattung ist zu gewähren.
  System: Die Rechnung betrifft den Kauf eines Fachbuchs, was nicht als "kleinere, zeitlich dringende Anschaffung" gilt. Nach Regel [EXP_SERVICE_REFERENCE] muss die Beschaffung über das SAP‑Beschaffungsprogramm erfolgen – die Rechnung liefert lediglich eine Auftragsnummer, keine Bestätigung der SAP‑Bestellung. Da die Voraussetzungen für eine Erstattung nicht erfüllt sind, wird der Antrag abgelehnt.
