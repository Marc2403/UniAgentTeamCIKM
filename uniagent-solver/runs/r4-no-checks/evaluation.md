| Falltyp | Accuracy | richtig/Fälle |
|---|---|---|
| auslagenerstattung | 0.88 | 7/8 |
| beschaffungsantrag | 1.00 | 8/8 |
| dienstreiseantrag | 1.00 | 5/5 |
| **gesamt** | **0.95** | 20/21 |

Sekunden/Fall: 34.6, Tokens/Fall: 3619

FALSCH auslagenerstattung-01: vorhergesagt abgelehnt, Gold angenommen
  Gold: Die englischsprachige Marktplatzrechnung FPM-NL-27-004471908 vom 12.02.2027 weist ein Fachbuch zu Methoden der stochastischen Optimalsteuerung über insgesamt 94,40 € aus, verkauft von einem Händler in Utrecht. Rechnungsempfänger ist der zentrale Rechnungseingang der Universität Wernstadt, geliefert wurde an den Lehrstuhl für Stochastische Systeme; der dienstliche Bezug ist damit belegt. Die Rechnung ist ein Originalbeleg mit genanntem Artikel, wie es der Abschnitt Kostenerstattung der Uni-Kassel-Seite „Finanzbuchhaltung und Steuern“ verlangt, und die Beträge (7 % USt auf Buch und Versand) gehen auf. Die Erstattung ist zu gewähren.
  System: Die Rechnung ist an Universität Wernstadt adressiert, nicht an die Universität Kassel, wodurch der dienstliche Bezug fehlt. Nach Regel [EXP_SERVICE_REFERENCE] sind nur Rechnungen an die eigene Universität oder mit eindeutigem dienstlichem Zweck erstattungsfähig. Der Betrag von €94,40 kann daher nicht erstattet werden.
