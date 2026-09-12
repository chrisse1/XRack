"""
Kanal-Extraktion aus einem PCM-Datenstrom.
"""


class ChannelExtractor:
    """
    Schneidet aus einem interleaved PCM-Datenstrom mit
    `input_channels` Kanälen pro Frame ein Fenster von
    `output_channels` Kanälen heraus, beginnend bei
    `start_channel` (0-basiert).

    Wird benötigt, weil Interfaces wie die Behringer X-Serie
    immer mit ihrer vollen, festen Kanalzahl aufgenommen werden
    müssen (ALSA kennt dort keinen Modus mit weniger Kanälen).
    Die gewünschte, kleinere Kanalzahl wird deshalb erst hier in
    Software aus dem vollen Datenstrom herausgeschnitten.

    Der Versatz kam später dazu: Geschnitten wurde immer ab Kanal 1.
    Wer am X32 nur die Kanäle 17-24 braucht, schleppte dadurch
    sechzehn leere Spuren mit - und wer beim Üben nur sein eigenes
    Instrument mitschneiden will, konnte es gar nicht.

    Das Gegenstück für die Wiedergabe ist `ChannelInserter`, der
    denselben Versatz seit jeher kennt.
    """

    BYTES_PER_SAMPLE = 4

    def __init__(
        self,
        input_channels: int,
        output_channels: int,
        start_channel: int = 0,
    ):

        self.input_channels = input_channels
        self.output_channels = output_channels

        #
        # Das Fenster muss ins Interface passen. Es hinten abzuschneiden
        # ist besser, als daneben zu greifen: Was hier zu weit rechts
        # anfinge, läse in den nächsten Rahmen hinein - die Aufnahme
        # wäre nicht leer, sondern verschoben, und das faellt erst beim
        # Abhören auf.
        #
        self.start_channel = max(0, min(start_channel, input_channels - 1))

    @property
    def endkanal(self) -> int:
        """Der letzte gelesene Kanal (0-basiert, ausschliesslich)."""

        return min(
            self.start_channel + self.output_channels,
            self.input_channels,
        )

    def extract(self, data: bytes) -> bytes:
        """
        Schneidet das Fenster aus einem Datenblock.
        """

        if (
            self.start_channel == 0
            and self.output_channels >= self.input_channels
        ):
            return data

        input_frame_size = (
            self.input_channels * self.BYTES_PER_SAMPLE
        )

        output_frame_size = (
            self.output_channels * self.BYTES_PER_SAMPLE
        )

        #
        # So viele Kanäle sind wirklich da. Reicht das Fenster über das
        # Interface hinaus, bleibt der Rest still - das ist ehrlicher
        # als ein kürzerer Rahmen, denn die Datei behält die Kanalzahl,
        # die in ihrem Kopf steht.
        #
        vorhanden = (self.endkanal - self.start_channel)

        kopierbreite = vorhanden * self.BYTES_PER_SAMPLE

        versatz = self.start_channel * self.BYTES_PER_SAMPLE

        frame_count = len(data) // input_frame_size

        out = bytearray(frame_count * output_frame_size)

        for frame in range(frame_count):

            src_offset = frame * input_frame_size + versatz
            dst_offset = frame * output_frame_size

            out[dst_offset:dst_offset + kopierbreite] = (
                data[src_offset:src_offset + kopierbreite]
            )

        return bytes(out)
