FROM nginx:1.27-alpine

# Configuración del reverse proxy
COPY nginx/nginx.conf /etc/nginx/nginx.conf

# Assets estáticos
COPY public/ /usr/share/nginx/html/

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD wget -qO- http://localhost/healthz || exit 1

CMD ["nginx", "-g", "daemon off;"]