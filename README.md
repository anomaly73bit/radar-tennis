# Radar Tennis

Robot che ogni 30 minuti legge le quote Unibet delle partite ATP e WTA di singolare non ancora iniziate, le confronta con un modello statistico e pubblica la pagina `docs/index.html` (GitHub Pages: https://anomaly73bit.github.io/radar-tennis/).

Codice nella cartella `robot/`:

- `sharp.py`: quote sharp (Pinnacle, Betfair Exchange, Matchbook) e Unibet da The Odds API (Secret `ODDS_API_KEY`).
- `tennis_model.py`: stato dei giocatori (Elo generale e per superficie, forma, stanchezza, scontri diretti, ranking) e modello.
- `export_state.py`: prepara `state.json`, `model.json` e `backtest.json` dai file storici di tennis-data.co.uk (`python export_state.py cartella_xlsx`).
- `robot.py`: aggiorna lo stato con i risultati ESPN, legge le quote Unibet (Kambi), registra le scommesse finte in `bets.json`, rigenera la pagina.

Giocate consigliate e simulate: quando la quota Unibet supera di almeno il 3% la quota giusta ricavata da Pinnacle/Betfair (senza margine), quota tra 1,20 e 6,00. Conto simulato da 200 €, 2% del conto a giocata. Nessuna scommessa vera viene piazzata.
