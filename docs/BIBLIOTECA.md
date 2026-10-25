# Biblioteca JFA Heredia

Esta rama adapta [uBiblio](https://github.com/seanboyce/ubiblio) para la biblioteca de la Juventud del Frente Amplio en Heredia. El servicio lo da una persona facilitadora en el mostrador. Las personas no piden libros por su cuenta.

La interfaz de uso diario está en castellano. El aspecto usa el negro y el amarillo de [La Jota](https://www.lajota.cr) y del [Frente Amplio](https://www.frenteamplio.org).

## Cambios respecto a uBiblio

- El nombre visible es **Biblioteca JFA Heredia**.
- El préstamo lo hace la persona administradora. Elige a la persona y asigna una copia.
- Cada persona se registra con nombre, apellido 1, apellido 2, provincia, cantón, distrito, dirección exacta, teléfono y correo.
- Esos datos personales se guardan cifrados en la base. La contraseña se guarda como huella, no como texto.
- Un mismo título puede tener varias copias. El sistema muestra cuántas quedan disponibles.
- Se pueden cargar libros en lote desde Excel o CSV.
- El escáner de ISBN está desactivado.
- Los libros electrónicos están desactivados y se encienden desde Administración.
- El acceso en línea de las personas usuarias está desactivado y se enciende desde Administración.
- Hay tema claro y tema oscuro.
- La instalación de red local publica solo HTTPS, limita los intentos de acceso y arranca con el sistema.

## Uso en el mostrador

1. Inicie sesión con la cuenta administradora.
2. En **Personas**, registre a quien llega.
3. En **Buscar**, abra la ficha del libro.
4. Elija a la persona y pulse **Prestar**. Cada préstamo descuenta una copia.
5. En **Préstamos pendientes** se ve quién tiene cada ejemplar, con teléfono y lugar. **Devolver** regresa esa copia al estante.

La ficha muestra editorial, páginas y las copias disponibles, por ejemplo **2 de 3**.

## Carga de libros

En **Agregar**, el primer botón es **Cargar Excel**. El archivo puede ser `.xlsx` o `.csv`. Se leen las primeras cinco columnas, en este orden:

| Autorías | Título | Editorial | Páginas | Cantidad |
|---|---|---|---|---|
| García Márquez | Cien años de soledad | Sudamericana | 471 | 3 |

La primera fila puede ser el encabezado. La columna de cantidad también se reconoce si se llama `Cant`. Si el título y la autoría ya existen, la cantidad se suma a las copias y a las disponibles. Las filas sin título se omiten.

La ubicación en el estante no viene en esa hoja. Queda vacía y se puede completar después al editar el libro.

## Administración

En **Administración** se guardan estas opciones:

| Opción | Efecto con el valor actual |
|---|---|
| Tema | **Claro** usa fondo gris. **Oscuro** usa fondo negro. En ambos se mantienen el amarillo y el negro de la organización. |
| Libros electrónicos | **No**: solo ejemplares físicos. **Sí**: se pueden marcar y filtrar libros electrónicos. |
| Acceso en línea | **No**: solo entra la persona facilitadora y ella presta. **Sí**: las personas registradas pueden iniciar sesión y pedir un préstamo. Queda para más adelante. |
| Imágenes de portada | Activa o desactiva las portadas. |
| Géneros | Lista separada por comas. |

La contraseña de una cuenta nueva debe tener al menos 8 caracteres.

## Puesta en marcha

La instalación prevista es una Raspberry Pi en la red local, con Docker.

```bash
cp deploy/lan.env.example .env
chmod 600 .env
```

En `.env` defina una contraseña hexadecimal para Redis (`openssl rand -hex 24`), el usuario y la contraseña de administración, `PUID`, `PGID` y `LAN_BIND`. `LAN_BIND=0.0.0.0` publica el puerto 443 en todas las interfaces de la Pi. Un certificado de ejemplo para una dirección IP se guarda en `deploy/certs/` (`ip.crt` y `ip.key`). Esa carpeta no se versiona.

```bash
docker compose -f docker-compose.lan.yml up -d
```

Abra `https://<dirección-de-la-pi>/user-setup/` una vez para crear la cuenta administradora. Después ponga `CREATE_ADMIN_USER=false` en `.env`, borre `ADMIN_PASSWORD` y vuelva a levantar el servicio.

Para que arranque al iniciar el sistema:

```bash
sudo cp deploy/ubiblio.service /etc/systemd/system/ubiblio.service
sudo systemctl daemon-reload
sudo systemctl enable --now ubiblio.service
```

Docker también debe estar habilitado. El servicio usa `docker compose up -d` después de que la red y Docker estén listos.

La imagen de la aplicación en la Pi es `ubiblio:arm64`. El código del repositorio se monta dentro del contenedor, así que un cambio de plantillas o de Python se aplica al reiniciar el servicio. El paquete `cryptography` tiene que estar instalado en la imagen; si se recrea el contenedor desde una imagen antigua, hay que instalarlo de nuevo antes de arrancar.

## Seguridad

- El nombre, los apellidos, la dirección, el teléfono y el correo se cifran antes de escribirse en SQLite. La clave sale de `SECRET_KEY`. Si esa clave cambia, los datos cifrados no se pueden leer. Respáldela aparte de un volcado suelto de la base.
- La contraseña no se puede recuperar: solo se guarda su huella.
- El usuario de acceso queda en claro porque es la llave para entrar.
- La sesión va en una cookie que el navegador no expone a JavaScript. En la instalación local solo viaja por HTTPS.
- Las acciones que cambian datos (borrar, devolver, restaurar) exigen una marca que la propia página conoce. Un sitio externo no puede activarlas con solo el enlace.
- Las descargas y las copias de seguridad solo aceptan un nombre de archivo dentro de su carpeta. Un ZIP se revisa antes de descomprimirlo para que no escriba fuera de esa carpeta.
- Redis limita los intentos de acceso. No está publicado hacia la red.
- Caddy es el único servicio que escucha en el puerto 443. La aplicación no se publica directamente.

## Origen

El programa base es uBiblio, de Sean Boyce. La plantilla visual parte de Forty, de HTML5 UP, y conserva esa atribución en el pie. Los cambios de esta rama están en `local-desk-and-lan`.
