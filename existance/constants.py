import string
from tempfile import gettempdir

EXISTDB_INSTALLER_URL = "https://bintray.com/existdb/releases/download_file" \
                        "?file_path=eXist-db-setup-${version}.jar"
LATEST_EXISTDB_RECORD_URL = 'https://api.github.com/repos/eXist-db/exist/' \
                            'releases/latest'
PASSWORD_CHARACTERS = string.ascii_letters + string.digits
TMP = gettempdir()
