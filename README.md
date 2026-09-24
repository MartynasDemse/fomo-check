# Ar verta prekiauti? Kasdienis patikrinimas

Puslapis, kuris kiekvieną rytą pats atsinaujina ir parodo, kiek iš tos pačios mėnesinės sumos liktų:
paprastam DCA (ETF + BTC), trendo filtrui ir 1000 atsitiktinių aktyvaus prekiautojo scenarijų.

Viskas veikia nemokamai GitHub'e: **Actions** kasdien paleidžia skriptą, **Pages** rodo puslapį.

## Įdiegimas (~15 min., vieną kartą)

1. **Sukurk repozitoriją** GitHub'e, pvz. `fomo-check`. Pasirink **Public** (nemokamas Pages veikia tik su vieša repozitorija).
2. **Įkelk failus**: *Add file → Upload files* ir nutempk visus šio aplanko failus.
   Jei aplankas `.github` neįsikelia (paslėpti aplankai kai kur nerodomi), sukurk jį ranka:
   *Add file → Create new file*, pavadinimas `.github/workflows/daily.yml`, įklijuok failo turinį.
3. **Leisk botui rašyti**: *Settings → Actions → General → Workflow permissions → Read and write permissions → Save*.
4. **Pirmas paleidimas**: *Actions → Kasdienis atnaujinimas → Run workflow*. Po ~2 min. turi atsirasti žalia varnelė.
5. **Įjunk puslapį**: *Settings → Pages → Source: Deploy from a branch → Branch: main, aplankas /docs → Save*.
6. Po minutės puslapis veiks adresu `https://<tavo-vardas>.github.io/fomo-check/`. Įsidėk į telefono pradžios ekraną.

Toliau jis atsinaujins kasdien 08:30 Vilniaus laiku.

## Kasdienis naudojimas

- **Pamatei „greito uždarbio“ schemą?** Įvesk jos skaičius į skaičiuoklę puslapyje.
- **Patikrinai ją?** Pridėk įrašą į `hype.json` (GitHub'e: atidaryk failą → pieštukas → pridėk bloką → *Commit*).
  Puslapyje jis atsiras po kito atnaujinimo arba iškart, jei rankiniu būdu paleisi *Run workflow*.

## Duomenų šaltiniai

- **BTC**: Binance `BTCEUR` dienos kainos (tie patys duomenys, kuriuos rodo TradingView Binance grafikai),
  per viešą rinkos duomenų adresą `data-api.binance.vision`, be jokio rakto.
  Laikotarpis iki Binance BTCEUR pradžios (2020 m. sausio) papildomas Yahoo `BTC-EUR` kainomis.
- **ETF**: Yahoo Finance `VWCE.DE`.
- Jei Binance neatsako, BTC automatiškai imamas iš Yahoo, o puslapio skiltyje „Kaip tai suskaičiuota“ matysi, kuris šaltinis naudotas.
- Jei Binance ir Yahoo kainos skiriasi daugiau nei 3 %, puslapio viršuje atsiras įspėjimas.

**Po pirmo paleidimo patikrink**: *Actions → paskutinis paleidimas → žingsnis „python fomo_check.py“*.
Turi matyti eilutę „Binance vs Yahoo BTC skirtumas…“. Jei vietoj jos yra „Binance nepasiekiamas“,
GitHub serveriai negauna Binance duomenų ir puslapis veiks su Yahoo. Tai irgi tinka.

## Nustatymai

Viršutinėje `fomo_check.py` dalyje: mėnesinė suma, ETF/BTC proporcija, ETF simbolis (`VWCE.DE`),
prekiautojo sandorių dažnis ir kaštai. Pakeitęs nusprendi pats, ar sąlygos sąžiningos. Tame ir esmė.

## Pastabos

- Puslapis viešas, bet jame tik hipotetiniai skaičiai ir tavo hype žurnalas. Asmeninių duomenų nėra.
- Jei Yahoo Finance kurią dieną neatsako, skriptas nieko nekeičia ir palieka vakarykštį puslapį.
- GitHub gali sustabdyti suplanuotus workflow neaktyviose repozitorijose. Jei gausi tokį laišką, įjunk vienu mygtuku *Actions* skiltyje.
- Tai istorinis modelis, ne investavimo rekomendacija.
