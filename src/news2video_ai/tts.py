import argparse
import asyncio
import base64
import re
import sys
from pathlib import Path

import edge_tts

PERSIAN_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")

ONES = [
    "صفر", "یک", "دو", "سه", "چهار", "پنج", "شش", "هفت", "هشت", "نه",
    "ده", "یازده", "دوازده", "سیزده", "چهارده", "پانزده", "شانزده",
    "هفده", "هجده", "نوزده",
]
TENS = ["", "", "بیست", "سی", "چهل", "پنجاه", "شصت", "هفتاد", "هشتاد", "نود"]
HUNDREDS = ["", "صد", "دویست", "سیصد", "چهارصد", "پانصد", "ششصد", "هفتصد", "هشتصد", "نهصد"]
SCALES = ["", "هزار", "میلیون", "میلیارد", "تریلیون"]
DECIMAL_SCALES = {
    1: "دهم",
    2: "صدم",
    3: "هزارم",
    4: "ده‌هزارم",
}


def integer_to_persian_words(number: int) -> str:
    """Convert a non-negative integer to natural Persian words."""
    if number == 0:
        return ONES[0]

    if number < 0:
        return f"منفی {integer_to_persian_words(abs(number))}"

    if number >= 10**15:
        # Extremely large identifiers are safer when read digit by digit.
        return " ".join(ONES[int(digit)] for digit in str(number))

    def under_thousand(value: int) -> str:
        parts = []
        hundreds, remainder = divmod(value, 100)

        if hundreds:
            parts.append(HUNDREDS[hundreds])

        if remainder:
            if remainder < 20:
                parts.append(ONES[remainder])
            else:
                tens, ones = divmod(remainder, 10)
                parts.append(TENS[tens])
                if ones:
                    parts.append(ONES[ones])

        return " و ".join(parts)

    groups = []
    scale_index = 0

    while number:
        number, group = divmod(number, 1000)
        if group:
            words = under_thousand(group)
            scale = SCALES[scale_index]
            if scale_index == 1 and group == 1:
                groups.append("هزار")
            else:
                groups.append(f"{words} {scale}".strip())
        scale_index += 1

    return " و ".join(reversed(groups))


def numeric_token_to_persian_words(token: str) -> str:
    """Convert an integer or decimal token to Persian words."""
    ascii_token = token.translate(PERSIAN_DIGITS).replace("٫", ".")

    if "." not in ascii_token:
        return integer_to_persian_words(int(ascii_token))

    integer_part, decimal_part = ascii_token.split(".", 1)
    decimal_part = decimal_part.rstrip("0")

    if not decimal_part:
        return integer_to_persian_words(int(integer_part))

    integer_words = integer_to_persian_words(int(integer_part))

    if len(decimal_part) <= 4:
        decimal_words = integer_to_persian_words(int(decimal_part))
        return (
            f"{integer_words} ممیز {decimal_words} "
            f"{DECIMAL_SCALES[len(decimal_part)]}"
        )

    digits = " ".join(ONES[int(digit)] for digit in decimal_part)
    return f"{integer_words} ممیز {digits}"


def normalize_numbers_for_tts(text: str) -> str:
    """Expand written digits, decimals and percentages for Persian TTS."""
    digit_class = "0-9۰-۹٠-٩"

    # Convert decimals before integers so their components are not split.
    number_pattern = re.compile(
        rf"(?<![{digit_class}])([{digit_class}]+(?:[\.٫][{digit_class}]+)?)(?![{digit_class}])"
    )

    normalized = number_pattern.sub(
        lambda match: numeric_token_to_persian_words(match.group(1)),
        text,
    )

    # Percent signs should be spoken after the expanded number.
    normalized = re.sub(r"\s*[%٪]", " درصد", normalized)
    return normalized


PRONUNCIATION_ENTRIES = [
    ("Baden-Württemberg", "بادن-وورتمبرگ", "بادِن وورْتِمبِرگ"),
    ("Bayern", "بایرن", "بایِرن"),
    ("Berlin", "برلین", "بِرلین"),
    ("Brandenburg", "براندنبورگ", "براندِن‌بورگ"),
    ("Bremen", "برمن", "بْرِمِن"),
    ("Hamburg", "هامبورگ", "هام‌بورگ"),
    ("Hessen", "هسن", "هِسِن"),
    ("Mecklenburg-Vorpommern", "مکلنبورگ-فورپومرن", "مِکلِن‌بورگ فورپومِرن"),
    ("Niedersachsen", "نیدرزاکسن", "نیدِر زاکسِن"),
    ("Nordrhein-Westfalen", "نوردراین-وستفالن", "نورْت‌راین وِست‌فالِن"),
    ("Rheinland-Pfalz", "راینلاند-فالتس", "راین‌لاند فالتس"),
    ("Saarland", "زارلاند", "زارلاند"),
    ("Sachsen", "زاکسن", "زاکسِن"),
    ("Sachsen-Anhalt", "زاکسن-آنهالت", "زاکسِن آنهالت"),
    ("Schleswig-Holstein", "اشلسویگ-هولشتاین", "شْلِسویگ هولشتاین"),
    ("Thüringen", "تورینگن", "تورینگِن"),
    ("Aachen", "آخن", "آخِن"),
    ("Augsburg", "آوگسبورگ", "آوگْس‌بورگ"),
    ("Bielefeld", "بیله‌فلد", "بیلِه‌فِلت"),
    ("Bochum", "بوخوم", "بوخوم"),
    ("Bonn", "بن", "بُن"),
    ("Braunschweig", "براونشوایگ", "براون‌شوایگ"),
    ("Chemnitz", "کمنیتس", "کِم‌نیتس"),
    ("Darmstadt", "دارمشتات", "دارم‌شتات"),
    ("Dortmund", "دورتموند", "دورتمونت"),
    ("Dresden", "درسدن", "دْرِسدِن"),
    ("Duisburg", "دویسبورگ", "دویس‌بورگ"),
    ("Düsseldorf", "دوسلدورف", "دوسِل‌دورف"),
    ("Erfurt", "ارفورت", "اِرفورت"),
    ("Essen", "اسن", "اِسِن"),
    ("Frankfurt am Main", "فرانکفورت آم ماین", "فرانک‌فورت آم ماین"),
    ("Freiburg im Breisgau", "فرایبورگ", "فرای‌بورگ"),
    ("Gelsenkirchen", "گلزن‌کیرشن", "گِلزِن‌کیرشِن"),
    ("Göttingen", "گوتینگن", "گوتینگِن"),
    ("Halle (Saale)", "هاله", "هالِه"),
    ("Hannover", "هانوفر", "هانوفِر"),
    ("Heidelberg", "هایدلبرگ", "هایدِل‌بِرگ"),
    ("Jena", "ینا", "یِنا"),
    ("Karlsruhe", "کارلسروهه", "کارلْس‌روهِه"),
    ("Kassel", "کاسل", "کاسِل"),
    ("Kiel", "کیل", "کیل"),
    ("Koblenz", "کوبلنتس", "کوبلِنتس"),
    ("Köln", "کلن", "کُلن"),
    ("Leipzig", "لایپزیگ", "لایپ‌تسیگ"),
    ("Lübeck", "لوبک", "لوبِک"),
    ("Magdeburg", "ماگدبورگ", "ماگدِبورگ"),
    ("Mainz", "ماینتس", "ماینتس"),
    ("Mannheim", "مانهایم", "مان‌هایم"),
    ("Mönchengladbach", "مونشن‌گلادباخ", "مونشِن گلادباخ"),
    ("München", "مونیخ", "مونیخ"),
    ("Münster", "مونستر", "مونستِر"),
    ("Nürnberg", "نورنبرگ", "نورن‌بِرگ"),
    ("Oberhausen", "اوبرهاوزن", "اوبِرهاوزِن"),
    ("Oldenburg", "اولدنبورگ", "اُلدِن‌بورگ"),
    ("Osnabrück", "اسنابروک", "اوسنا‌بروک"),
    ("Potsdam", "پوتسدام", "پوتس‌دام"),
    ("Regensburg", "رگنسبورگ", "رِگِنس‌بورگ"),
    ("Rostock", "روستوک", "روستوک"),
    ("Saarbrücken", "زاربروکن", "زار‌بروکِن"),
    ("Stuttgart", "اشتوتگارت", "شْتوت‌گارت"),
    ("Wiesbaden", "ویسبادن", "ویس‌بادِن"),
    ("Wolfsburg", "ولفسبورگ", "وُلفس‌بورگ"),
    ("Wuppertal", "ووپرتال", "ووپِرتال"),
    ("CDU", "CDU", "سِ دِ او"),
    ("CSU", "CSU", "سِ اِس او"),
    ("CDU/CSU", "CDU/CSU", "سِ دِ او و سِ اِس او"),
    ("SPD", "SPD", "اِس پِ دِ"),
    ("AfD", "AfD", "آ اِف دِ"),
    ("Bündnis 90/Die Grünen", "اتحاد ۹۰/سبزها", "اتحاد نود و سبزها"),
    ("Die Grünen", "سبزها", "سبزها"),
    ("Die Linke", "حزب چپ", "حزب چپ"),
    ("FDP", "FDP", "اِف دِ پِ"),
    ("BSW", "ائتلاف زارا واگن‌کنشت", "ائتلاف زارا واگِن‌کِنِشت"),
    ("Freie Wähler", "رأی‌دهندگان آزاد", "رأی‌دهندگان آزاد"),
    ("Volt Deutschland", "ولت آلمان", "وُلت آلمان"),
    ("Die PARTEI", "دی پارتی", "دی پارْتای"),
    ("Die Heimat", "دی هایمات", "دی هایمات"),
    ("Bundestag", "بوندستاگ", "بوندِس‌تاگ"),
    ("Bundesrat", "بوندسرات", "بوندِس‌رات"),
    ("Bundesregierung", "دولت فدرال آلمان", "دولت فدرال آلمان"),
    ("Bundeskanzleramt", "دفتر صدراعظم آلمان", "دفتر صدراعظم آلمان"),
    ("Bundesverfassungsgericht", "دادگاه قانون اساسی فدرال", "دادگاه قانون اساسی فدرال"),
    ("Bundesgerichtshof", "دیوان عالی فدرال", "دیوان عالی فدرال"),
    ("Bundeswehr", "ارتش آلمان", "ارتش آلمان"),
    ("Bundespolizei", "پلیس فدرال آلمان", "پلیس فدرال آلمان"),
    ("BKA", "BKA", "بِ کا آ"),
    ("BND", "BND", "بِ اِن دِ"),
    ("BfV", "BfV", "بِ اِف فاو"),
    ("LKA", "LKA", "اِل کا آ"),
    ("BAMF", "BAMF", "بامف"),
    ("BaFin", "بافین", "با‌فین"),
    ("Bundesagentur für Arbeit", "آژانس فدرال کار آلمان", "آژانس فدرال کار آلمان"),
    ("Bundesbank", "بوندس‌بانک", "بوندِس‌بانک"),
    ("Bundesnetzagentur", "سازمان تنظیم شبکه‌های آلمان", "سازمان تنظیم شبکه‌های آلمان"),
    ("Bundeskartellamt", "اداره فدرال ضدانحصار", "اداره فدرال ضد انحصار"),
    ("Robert Koch-Institut", "مؤسسه روبرت کخ", "مؤسسه روبِرت کُخ"),
    ("RKI", "RKI", "اِر کا ای"),
    ("Paul-Ehrlich-Institut", "مؤسسه پاول ارلیش", "مؤسسه پاول اِرلیش"),
    ("ARD", "ARD", "آ اِر دِ"),
    ("ZDF", "ZDF", "تسِت دِ اِف"),
    ("Deutschlandfunk", "دویچلندفونک", "دویچ‌لاند فونک"),
    ("Deutsche Welle", "دویچه‌وله", "دویچِه وِلِه"),
    ("Tagesschau", "تاگس‌شاو", "تاگِس‌شاو"),
    ("Lufthansa", "لوفت‌هانزا", "لوفت‌هانزا"),
    ("Deutsche Bahn", "راه‌آهن آلمان", "راه‌آهن آلمان"),
    ("Volkswagen", "فولکس‌واگن", "فولکس‌واگِن"),
    ("Mercedes-Benz", "مرسدس بنز", "مِرسِدِس بِنز"),
    ("Europäische Union", "اتحادیه اروپا", "اتحادیه اروپا"),
    ("EU", "EU", "اِ او"),
    ("NATO", "ناتو", "ناتو"),
    ("UNO", "سازمان ملل متحد", "سازمان ملل متحد"),
    ("UN", "سازمان ملل متحد", "سازمان ملل متحد"),
    ("Europäische Kommission", "کمیسیون اروپا", "کمیسیون اروپا"),
    ("Europäischer Rat", "شورای اروپا", "شورای اروپا"),
    ("Europäisches Parlament", "پارلمان اروپا", "پارلمان اروپا"),
    ("Europäische Zentralbank", "بانک مرکزی اروپا", "بانک مرکزی اروپا"),
    ("EZB", "EZB", "اِ تْسِت بِ"),
    ("OSZE", "سازمان امنیت و همکاری اروپا", "سازمان امنیت و همکاری اروپا"),
    ("Internationaler Strafgerichtshof", "دیوان کیفری بین‌المللی", "دیوان کیفری بین‌المللی"),
    ("IStGH", "دیوان کیفری بین‌المللی", "دیوان کیفری بین‌المللی"),
    ("WHO", "سازمان جهانی بهداشت", "سازمان جهانی بهداشت"),
    ("Internationaler Währungsfonds", "صندوق بین‌المللی پول", "صندوق بین‌المللی پول"),
    ("IWF", "صندوق بین‌المللی پول", "صندوق بین‌المللی پول"),
    ("Frank-Walter Steinmeier", "فرانک-والتر اشتاین‌مایر", "فرانک والتر اشتاین‌مایِر"),
    ("Friedrich Merz", "فریدریش مرتس", "فریدریش مِرتس"),
    ("Julia Klöckner", "یولیا کلوکنر", "یولیا کْلُکنِر"),
    ("Lars Klingbeil", "لارس کلینگ‌بایل", "لارس کلینگ‌بایل"),
    ("Alexander Dobrindt", "الکساندر دوبرینت", "اَلِکساندِر دوبْرینت"),
    ("Johann Wadephul", "یوهان واده‌فول", "یوهان وادِفول"),
    ("Boris Pistorius", "بوریس پیستوریوس", "بوریس پیستوریوس"),
    ("Katherina Reiche", "کاترینا رایخه", "کاتِرینا رایخِه"),
    ("Dorothee Bär", "دوروتِه بِر", "دوروتِه بِر"),
    ("Stefanie Hubig", "اشتفانی هوبیگ", "شْتِفانی هوبیگ"),
    ("Karin Prien", "کارین پرین", "کارین پرین"),
    ("Bärbel Bas", "بربل باس", "بِربِل باس"),
    ("Karsten Wildberger", "کارستن ویلدبرگر", "کارستِن ویلد‌بِرگِر"),
    ("Steffen Bilger", "اشتفن بیلگر", "شْتِفِن بیلگِر"),
    ("Carsten Schneider", "کارستن اشنایدر", "کارستِن شْنایْدِر"),
    ("Carsten Linnemann", "کارستن لینمان", "کارستِن لینِمان"),
    ("Alois Rainer", "آلویس راینر", "آلویس رایْنِر"),
    ("Reem Alabali-Radovan", "ریم العَبالی-رادوان", "ریم اَلعَبالی رادوان"),
    ("Verena Hubertz", "ورنا هوبرتس", "وِرِنا هوبِرتس"),
    ("Nina Warken", "نینا وارکن", "نینا وارکِن"),
    ("Philipp Amthor", "فیلیپ آمتور", "فیلیپ آم‌تور"),
    ("Markus Söder", "مارکوس زودر", "مارکوس زودِر"),
    ("Alice Weidel", "آلیس وایدل", "آلیس وایْدِل"),
    ("Tino Chrupalla", "تینو کروپالا", "تینو کْروپالا"),
    ("Franziska Brantner", "فرانتسیسکا برانتنر", "فرانتسیسکا برانتنِر"),
    ("Felix Banaszak", "فلیکس باناشاک", "فِلیکس باناشاک"),
    ("Jan van Aken", "یان فان آکن", "یان فان آکِن"),
    ("Ines Schwerdtner", "اینس شوِرتنر", "اینس شْوِرت‌نِر"),
    ("Christian Dürr", "کریستیان دور", "کریستیان دور"),
    ("Sahra Wagenknecht", "زارا واگن‌کنشت", "زارا واگِن‌کِنِشت"),
    ("Olaf Scholz", "اولاف شولتس", "اولاف شولتس"),
    ("Annalena Baerbock", "آنالنا بربوک", "آنالِنا بِربوک"),
    ("Robert Habeck", "روبرت هابک", "روبِرت هابِک"),
    ("Christian Lindner", "کریستیان لیندنر", "کریستیان لیندْنِر"),
    ("Angela Merkel", "آنگلا مرکل", "آنگِلا مِرکِل"),
    ("Ursula von der Leyen", "اورسولا فون‌درلاین", "اورزولا فون دِر لایِن"),
    ("António Costa", "آنتونیو کوستا", "آنتونیو کوستا"),
    ("Roberta Metsola", "روبرتا متسولا", "روبِرتا مِتسولا"),
    ("Kaja Kallas", "کایا کالاس", "کایا کالاس"),
    ("Christine Lagarde", "کریستین لاگارد", "کریستین لاگارد"),
    ("Mark Rutte", "مارک روته", "مارک روتِه"),
    ("António Guterres", "آنتونیو گوترش", "آنتونیو گوتِرِش"),
    ("Donald Trump", "دونالد ترامپ", "دونالد ترامپ"),
    ("JD Vance", "جی‌دی ونس", "جِی دی وِنس"),
    ("Joe Biden", "جو بایدن", "جو بایدِن"),
    ("Keir Starmer", "کیر استارمر", "کیر استارمِر"),
    ("Emmanuel Macron", "امانوئل مکرون", "اِمانوئل مَکرون"),
    ("Marine Le Pen", "مارین لوپن", "مارین لو پِن"),
    ("Giorgia Meloni", "جورجا ملونی", "جورجا مِلونی"),
    ("Pedro Sánchez", "پدرو سانچز", "پِدرو سانچِز"),
    ("Donald Tusk", "دونالد توسک", "دونالد توسک"),
    ("Viktor Orbán", "ویکتور اوربان", "ویکتور اُربان"),
    ("Volodymyr Zelenskyy", "ولودیمیر زلنسکی", "وولودیمیر زِلِنسکی"),
    ("Vladimir Putin", "ولادیمیر پوتین", "ولادیمیر پوتین"),
    ("Sergey Lavrov", "سرگئی لاوروف", "سِرگِی لاوروف"),
    ("Recep Tayyip Erdoğan", "رجب طیب اردوغان", "رَجَب طَیِب اِردوغان"),
    ("Benjamin Netanyahu", "بنیامین نتانیاهو", "بِنیامین نِتانیاهو"),
    ("Mahmoud Abbas", "محمود عباس", "محمود عَباس"),
    ("Ali Khamenei", "علی خامنه‌ای", "علی خامنه‌ای"),
    ("Ali Chamenei", "علی خامنه‌ای", "علی خامنه‌ای"),
    ("Ayatollah Ali Khamenei", "آیت‌الله علی خامنه‌ای", "آیت‌الله علی خامنه‌ای"),
    ("Ajatollah Ali Chamenei", "آیت‌الله علی خامنه‌ای", "آیت‌الله علی خامنه‌ای"),
    ("Mojtaba Khamenei", "مجتبی خامنه‌ای", "مُجتبی خامنه‌ای"),
    ("Mojtaba Chamenei", "مجتبی خامنه‌ای", "مُجتبی خامنه‌ای"),
    ("Modschtaba Khamenei", "مجتبی خامنه‌ای", "مُجتبی خامنه‌ای"),
    ("Modschtaba Chamenei", "مجتبی خامنه‌ای", "مُجتبی خامنه‌ای"),
    ("Masoud Pezeshkian", "مسعود پزشکیان", "مسعود پزشکیان"),
    ("Mohammad Javad Zarif", "محمدجواد ظریف", "محمّد جواد ظریف"),
    ("Mohammed bin Salman", "محمد بن سلمان", "محمّد بِن سَلمان"),
    ("Xi Jinping", "شی جین‌پینگ", "شی جین پینگ"),
    ("Narendra Modi", "نارندرا مودی", "نارِندرا مودی"),
    ("Kim Jong Un", "کیم جونگ اون", "کیم جونگ اون"),
]


def normalize_for_tts(text: str) -> str:
    """Replace display spellings and source names with TTS-friendly Persian."""
    normalized = normalize_numbers_for_tts(text)

    # Longest terms first prevents a short alias from changing a longer name.
    entries = sorted(
        PRONUNCIATION_ENTRIES,
        key=lambda entry: max(len(entry[0]), len(entry[1])),
        reverse=True,
    )

    for source, display_fa, tts_fa in entries:
        if source and source != tts_fa:
            normalized = normalized.replace(source, tts_fa)

        if display_fa and display_fa != tts_fa:
            normalized = normalized.replace(display_fa, tts_fa)

    return " ".join(normalized.split())


async def generate_speech(
    text: str,
    output: Path,
    voice: str,
    rate: str,
    pitch: str,
) -> None:
    text = text.strip()

    if not text:
        raise ValueError("TTS text is empty.")

    output.parent.mkdir(parents=True, exist_ok=True)

    communicate = edge_tts.Communicate(
        text=text,
        voice=voice,
        rate=rate,
        pitch=pitch,
    )

    await communicate.save(str(output))


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate Persian audio with Edge TTS."
    )

    text_group = parser.add_mutually_exclusive_group(required=True)

    text_group.add_argument(
        "--text",
        help="Plain UTF-8 text.",
    )

    text_group.add_argument(
        "--text-base64",
        help="UTF-8 text encoded as Base64.",
    )

    parser.add_argument("--output", required=True)

    parser.add_argument(
        "--voice",
        default="fa-IR-FaridNeural",
    )

    parser.add_argument(
        "--rate",
        default="-5%",
    )

    parser.add_argument(
        "--pitch",
        default="-2Hz",
    )

    return parser.parse_args()


def resolve_text(args: argparse.Namespace) -> str:
    if args.text is not None:
        return args.text

    try:
        decoded_bytes = base64.b64decode(
            args.text_base64,
            validate=True,
        )

        return decoded_bytes.decode("utf-8")

    except Exception as error:
        raise ValueError(
            f"Invalid Base64 TTS text: {error}"
        ) from error


async def main() -> None:
    args = parse_arguments()
    output_path = Path(args.output).resolve()

    try:
        text = normalize_for_tts(resolve_text(args))

        await generate_speech(
            text=text,
            output=output_path,
            voice=args.voice,
            rate=args.rate,
            pitch=args.pitch,
        )

        print(f"TTS_SUCCESS:{output_path}")

    except Exception as error:
        print(f"TTS_ERROR:{error}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
