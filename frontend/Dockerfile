FROM node:20-slim

WORKDIR /app

COPY package.json /app/package.json
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

EXPOSE 5173
ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["npm", "run", "dev"]
