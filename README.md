# LinkedIn Analytics Apify

Scraper automatizzato per estrarre statistiche da LinkedIn Creator Analytics da utilizzare con Apify e n8n.

## Descrizione

Questo progetto fornisce uno scraper Python che automatizza l'estrazione di metriche e statistiche dalla pagina LinkedIn Creator Analytics. Lo script è progettato per essere integrato con Apify come actor e successivamente utilizzato in flussi di lavoro n8n.

## Funzionalità

Lo script è in grado di estrarre:

- **Impressioni totali**: numero totale di visualizzazioni dei contenuti
- **Utenti raggiunti**: spettatori unici
- **Reazioni**: numero totale di like/reazioni
- **Commenti**: numero totale di commenti
- **Condivisioni**: numero di repost
- **Nuovi follower**: crescita della rete
- **Engagement rate**: tasso di coinvolgimento
- **Metriche per singolo post**: impressioni, likes, commenti per ogni post
- **Hashtag utilizzati**: analisi degli hashtag presenti nei contenuti
- **Trend temporali**: analisi delle tendenze con linee di regressione

## Come funziona

1. **Login automatico**: Lo script effettua il login su LinkedIn utilizzando le credenziali fornite
2. **Navigazione**: Accede alla pagina Creator Analytics (sezione Content)
3. **Scrolling**: Scorre la pagina per caricare tutti i post richiesti
4. **Estrazione dati**: Analizza l'HTML della pagina per estrarre tutte le metriche
5. **Elaborazione**: Processa i dati, rimuove outlier e calcola trend
6. **Export**: Salva i risultati in formato CSV e genera grafici PNG

## Input richiesti

Per utilizzare lo script con Apify, è necessario fornire i seguenti parametri nello schema JSON:

- **username**: Email o numero di telefono utilizzato per il login LinkedIn
- **password**: Password dell'account LinkedIn
- **profile_slug**: Username presente nel link del profilo (dopo '/in/')
- **num_posts** (opzionale): Numero di post da analizzare (default: 10)

### Esempio schema JSON per Apify:

```json
{
  "username": "tua-email@esempio.com",
  "password": "tua-password-sicura",
  "profile_slug": "tuo-username-linkedin",
  "num_posts": 10
}
```

## Output

Lo script genera diversi file di output:

- `analytics_impressioni_utenti.csv`: CSV con impressioni totali e utenti raggiunti
- `analytics_totals.csv`: CSV con tutte le metriche aggregate
- `analytics_page.html`: HTML completo della pagina analytics (se abilitato)
- `analytics_posts_blocks.html`: HTML dei singoli blocchi post
- Grafici PNG con trend temporali (se abilitati)

## Integrazione con n8n

Dopo aver configurato l'actor su Apify:

1. Crea un nodo Apify in n8n
2. Seleziona l'actor "linkedin-analytics-apify"
3. Fornisci i parametri di input (username, password, profile_slug)
4. Processa i risultati nei nodi successivi del workflow

## Dipendenze

Lo script utilizza le seguenti librerie Python:

- `selenium`: per l'automazione del browser
- `beautifulsoup4`: per il parsing HTML
- `pandas`: per l'elaborazione dati
- `numpy`: per i calcoli statistici
- `matplotlib`: per la generazione di grafici
- `webdriver-manager`: per la gestione del driver Chrome
- `pyperclip`: per la gestione della clipboard

## Note importanti

⚠️ **Attenzione**: L'automazione di LinkedIn potrebbe violare i Termini di Servizio della piattaforma. Utilizzare questo script in modo responsabile e a proprio rischio.

## Licenza

Questo progetto è fornito "così com'è" senza garanzie di alcun tipo. L'utilizzo è a rischio dell'utente.

## Struttura del progetto

```
linkedin-analytics-apify/
├── README.md
└── linkedin_creator_content_scraper.py
```
