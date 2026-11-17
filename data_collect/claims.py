"""Map free text (title, description, bullets) to canonical claim labels in the app's three list fields
(claims / free_from / seals, see backend/app/pipeline/compare.py). Each hit keeps the sentence it came from."""
import re

# (field, canonical label, pattern). Patterns cover English plus the common FR/DE/IT/ES/PT wordings.
RULES = [
    ("free_from", "Fragrance Free", r"fragrance[- ]free|free (of|from) (added )?fragrance|unscented|without (added )?fragrance|parf[uü]m(frei| free)|sans parfum|senza profum|sin perfume|sem perfume"),
    ("free_from", "Paraben Free", r"paraben[- ]?free|free (of|from) parabens|no parabens|parabenfrei|sans parab[eè]ne|senza parabeni|sin parabenos"),
    ("free_from", "Alcohol Free", r"alcohol[- ]free|zero alcohol|0% alcohol|no alcohol|alkoholfrei|sans alcool|senza alcol|sin alcohol|sem [aá]lcool"),
    ("free_from", "Soap Free", r"soap[- ]free|seifenfrei|sans savon|senza sapone|sin jab[oó]n"),
    ("free_from", "Sulfate Free", r"sulfate[- ]free|sulphate[- ]free|free (of|from) sulfates|sulfatfrei|sans sulfates?"),
    ("free_from", "Dye Free", r"dye[- ]free|free (of|from) dyes|no dyes|colou?rant[- ]free"),
    ("free_from", "Phthalate Free", r"phthalate[- ]free"),
    ("free_from", "Steroid Free", r"steroid[- ]free"),
    ("free_from", "Silicone Free", r"silicone[- ]free|silikonfrei"),
    ("seals", "NEA Seal of Acceptance", r"national eczema association|nea seal|seal of acceptance from the nea"),
    ("seals", "ADA Seal of Acceptance", r"\bada\b (seal|accepted)|american dental association"),
    ("claims", "Kills 99.9% of germs", r"kills? (up to )?99(\.9)?\s?% of (bad[- ]breath |odou?r[- ]causing )?(germs|bacteria)|t[oö]tet 99|[ée]limine 99|elimina (il )?99"),
    ("claims", "Dermatologist recommended", r"dermatologist[- ]recommended|recommended by dermatologists|von dermatologen empfohlen|recommand[ée] par (les )?dermatologues"),
    ("claims", "Dermatologist tested", r"dermatologically[- ]tested|dermatologist[- ]tested|dermatologisch getestet|test[ée] sous contr[oô]le dermatologique|dermatologicamente testat"),
    ("claims", "Pediatrician recommended", r"pa?ediatrician[- ]recommended|recommended by pa?ediatricians"),
    ("claims", "Clinically proven", r"clinically[- ](proven|shown|tested)|klinisch (getestet|erwiesen|bewiesen)|cliniquement (prouv|test)|clinicamente (provat|testat|comprovad)"),
    ("claims", "24-hour moisture", r"24[- ]?(hour|hr|h|stunden|heures|ore|horas)s? ?(of )?(moisture|moisturi[sz]ation|hydration|feuchtigkeit|hydratation|idratazione|hidrataci[oó]n)|moisturi[sz]es for 24|hydrates for 24"),
    ("claims", "48-hour moisture", r"48[- ]?(hour|hr|h)s? ?(of )?(moisture|hydration)"),
    ("claims", "Hypoallergenic", r"hypo-?allergen|hipoalerg|ipoallergenic"),
    ("claims", "Non-comedogenic", r"non[- ]?comedogenic|nicht komedogen|non com[ée]dog[eè]ne|non comedogen|no comedog"),
    ("claims", "Tear free", r"tear[- ]free|no more tears|ohne tr[aä]nen|sans larmes"),
    ("claims", "Contains colloidal oatmeal", r"colloidal oat|kolloidale[mn]? hafer|avoine colloïdale|avena colloidale"),
    ("claims", "Contains prebiotic oat", r"prebiotic oat|pr[ée]biotique.{0,20}avoine|pr[äa]biotisch.{0,20}hafer"),
    ("claims", "For sensitive skin", r"(for|suitable for) sensitive skin|f[üu]r empfindliche haut|peaux? sensibles?|pelli sensibili|piel sensible"),
    ("claims", "Relieves eczema", r"eczema[- ]prone|eczema relief|eczema therapy|for eczema|(relie|sooth|calm|protect)\w* .{0,40}eczema|neurodermitis|peaux? à tendance atopique"),
    ("claims", "Relieves itchy skin", r"(relie|sooth|calm)\w* .{0,30}itch|itch[- ]relief|anti[- ]itch|juckreiz|d[ée]mangeaison|prurito|picaz[oó]n"),
    ("claims", "Broad spectrum SPF", r"broad[- ]spectrum"),
    ("claims", "Water resistant", r"water[- ]resistant|wasserfest|r[ée]sistant [àa] l.eau"),
    ("claims", "Reduces plaque", r"(reduces?|fights?|removes?|prevents?) (\w+ ){0,2}plaque|plaque[- ]reduc|gegen plaque|contre la plaque"),
    ("claims", "Fights gingivitis", r"gingivitis|gum disease|gingivite|zahnfleischentz[üu]ndung|gengivite"),
    ("claims", "Fights bad breath", r"bad breath|halitosis|mundgeruch|mauvaise haleine|alito cattivo|mal aliento|mau h[aá]lito"),
    ("claims", "Tartar control", r"tartar|zahnstein|tartre|tartaro|sarro"),
    ("claims", "Prevents cavities", r"cavit(y|ies)|karies|caries|carie"),
    ("claims", "Strengthens enamel", r"(strengthens?|restores?|rebuilds?) (\w+ ){0,2}enamel|zahnschmelz|[ée]mail|smalto|esmalte"),
    ("claims", "Whitening", r"whiten|aufhell|blanchi|sbianc|blanque|clareamento"),
    ("claims", "Contains fluoride", r"fluorid|fluor(ure|uro|eto)"),
    ("claims", "Fresh breath", r"fresh(er)? breath|frischer atem|haleine fra[iî]che|alito fresco|aliento fresco|h[aá]lito fresco"),
    ("claims", "Sensitive teeth", r"sensitive teeth|sensitivity|empfindliche z[äa]hne|dents sensibles|denti sensibili"),
    ("claims", "Vegan", r"\bvegan"),
    ("claims", "Cruelty free", r"cruelty[- ]free|not tested on animals"),
    ("claims", "Natural ingredients", r"naturally[- ]derived|natural ingredients|nat[üu]rliche inhaltsstoffe|ingr[ée]dients? naturels?"),
]
COMPILED = [(f, lab, re.compile(p, re.I)) for f, lab, p in RULES]
ORAL = {"Kills 99.9% of germs", "Reduces plaque", "Fights gingivitis", "Fights bad breath", "Tartar control",
        "Prevents cavities", "Strengthens enamel", "Whitening", "Contains fluoride", "Fresh breath", "Sensitive teeth",
        "ADA Seal of Acceptance"}
SKIN = {"Contains colloidal oatmeal", "Contains prebiotic oat", "For sensitive skin", "Relieves eczema",
        "Relieves itchy skin", "Broad spectrum SPF", "Water resistant", "24-hour moisture", "48-hour moisture",
        "Non-comedogenic", "Tear free", "Pediatrician recommended", "NEA Seal of Acceptance", "Soap Free",
        "Sulfate Free", "Silicone Free", "Steroid Free", "Hypoallergenic"}
OFF_BRAND = {"Aveeno": ORAL, "Listerine": SKIN}
# Ingredient lists mention words like "fluoride" or "oat"; only scan marketing text, not INCI.


def split_sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+|\s*\|\s*|\n", text or "") if s.strip()]


def extract_claims(texts: list[str], brand: str = "") -> dict[str, list[tuple[str, str]]]:
    """Return {field: [(label, quote), ...]} with one entry per label (first quote wins).
    Oral-care labels are not applied to Aveeno, skin labels not to Listerine (e.g. 'sensitivity')."""
    out: dict[str, dict[str, str]] = {"claims": {}, "free_from": {}, "seals": {}}
    skip = OFF_BRAND.get(brand, set())
    for t in texts:
        for sent in split_sentences(t):
            for field, label, rx in COMPILED:
                if label in skip:
                    continue
                if label not in out[field] and rx.search(sent):
                    out[field][label] = sent[:500]
    return {f: list(d.items()) for f, d in out.items()}
