"""Source-based policy coverage, independent of case IDs and reference labels."""
import re
from decimal import Decimal

# These are review topics, not policy conclusions or hard-coded thresholds.
TOPICS = {
 'business_trip': 'Genehmigung Finanzierung Dienstzweck Reisewarnung Reiseverbot Nebentätigkeit Honorar Onlineveranstaltung Inlandsflug Übernachtung Ausnahme private Verlängerung Drittmittel A1',
 'expense_reimbursement': 'Erstattung Zahlungsbeleg dienstlicher Bezug Gutschrift doppelt Bewirtung Gäste Geschenk Dekoration Software Lizenz Rahmenvertrag Beschaffungsweg',
 'procurement': 'Beschaffungsbefugnis Unterschrift Auftraggeber Direktvergabe Wertgrenze netto Gesamtbedarf Aufteilung Rahmenvertrag Produktgruppe wirtschaftlich Eignung Abweichung Rechnung',
}

def policy_excerpt(text, query, budget=16000):
    """Keep full short pages; rank paragraph-sized windows on long pages.

    A match includes adjacent context so qualifiers and exceptions survive.
    Source text is never rewritten and removed spans are explicitly marked.
    """
    if len(text)<=budget:return text
    terms={w.casefold() for w in re.findall(r'\w+',query) if len(w)>3}
    width=1600;overlap=400
    spans=[(s,min(s+width,len(text))) for s in range(0,len(text),width-overlap)]
    def score(span):
        body=text[span[0]:span[1]].casefold()
        return sum(min(body.count(t),3) for t in terms)
    chosen=[];used=0
    for start,end in sorted(spans,key=score,reverse=True):
        # Do not cut a paragraph/line when its boundary is nearby.
        left=text.rfind('\n',max(0,start-300),start)
        if left>=0:start=left+1
        right=text.find('\n',end,min(len(text),end+300))
        if right>=0:end=right
        if any(start>=a and end<=b for a,b in chosen):continue
        if used+end-start>budget:continue
        chosen.append((start,end));used+=end-start
    merged=[]
    for start,end in sorted(chosen):
        if merged and start<=merged[-1][1]:merged[-1]=(merged[-1][0],max(end,merged[-1][1]))
        else:merged.append((start,end))
    return '\n[… source passage omitted …]\n'.join(text[a:b] for a,b in merged)


def review_instructions(case_type):
    return ('\nQUELLENGESTÜTZTE FREIGABEPRÜFUNG: Prüfe vor der Entscheidung ausdrücklich folgende Themen, '
        'soweit auf diesen konkreten Fall anwendbar: '+TOPICS[case_type]+'. '
        'Ein dienstlicher Zweck, vollständige Belege oder drei Angebote allein belegen noch keine Zulässigkeit. '
        'Suche auch Verbote, verpflichtende Beschaffungswege, Zuständigkeiten und Ausnahmen in den P-Quellen. '
        'Eine Ausnahme ist zu prüfen, bevor ein Verstoß festgestellt wird. Wende Regeln nur für die passende '
        'Institution, Produktgruppe, Verfahrensstufe und den maßgeblichen Zeitraum an. '
        'Ein Suchbegriff ist KEINE Regel: Erfinde keine Verbote oder Wertgrenzen aus dieser Themenliste. '
        'Verwende die konkrete zitierte Vorschrift; unterscheide unbekannte Regelabdeckung von einem belegten Verstoß. '
        'Nenne in begruendung die entscheidenden bestandenen und nicht bestandenen Prüfungen einschließlich '
        'Regel-Ausnahme und konkretem Beleg. Bei Beträgen unterscheide netto/brutto, Stückpreis/Gesamtbedarf '
        'und bereits übernommene von erneut beantragten Kosten. '
        'Gib eine kurze Begründung (höchstens 180 Wörter) und das vollständige Entscheidungs-JSON aus.\n')


def explicit_sum_checks(documents):
    """Check explicit decimal addition equations, without guessing which numbers belong together.

    Findings are evidence for the reviewer, never automatic accept/reject rules.
    """
    number=r'(?:\d{1,3}(?:\.\d{3})*,\d{2}|\d+,\d{2}|\d+\.\d{2})'
    pattern=re.compile(rf'(?<![\w.,])({number}(?:\s*\+\s*{number})+)\s*=\s*({number})(?![\d,]|\.\d)')
    def decimal(value):return Decimal(value.replace('.','').replace(',','.')) if ',' in value else Decimal(value)
    checks=[]
    for filename,text in documents.items():
        for match in pattern.finditer(text):
            amounts=[decimal(x.strip()) for x in match.group(1).split('+')]
            total=sum(amounts,Decimal('0'));expected=decimal(match.group(2))
            checks.append({'filename':filename,'quote':match.group(0),'computed_sum':str(total),'stated_sum':str(expected),'matches':abs(total-expected)<=Decimal('0.01')})
    return checks
