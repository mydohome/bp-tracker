FROM nginx:alpine

# Scarichiamo Chart.js durante la build dell'immagine (una tantum, con
# accesso a internet della macchina che fa la build) e lo serviamo poi
# dal nostro stesso server nginx. In questo modo il browser dell'utente
# non deve MAI raggiungere un CDN esterno a runtime: niente più rotture
# per blocchi DNS, ad-blocker, firewall aziendali o reti che filtrano
# cdnjs.cloudflare.com.
#
# Usiamo l'alias di versione maggiore "@4" di jsDelivr (non un numero di
# build fisso come "4.4.4"): risolve sempre automaticamente all'ultima
# versione stabile della serie 4.x, quindi non si rompe se una build
# specifica smette di essere ospitata dal CDN durante il tempo.
RUN apk add --no-cache curl && \
    curl -fsSL https://cdn.jsdelivr.net/npm/chart.js@4/dist/chart.umd.min.js \
      -o /usr/share/nginx/html/chart.umd.min.js && \
    apk del curl

COPY index.html /usr/share/nginx/html/index.html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
