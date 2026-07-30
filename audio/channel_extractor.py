"""
Kanal-Extraktion aus einem PCM-Datenstrom.
"""


class ChannelExtractor:
    """
    Schneidet aus einem interleaved PCM-Datenstrom mit
    `input_channels` Kanälen pro Frame die ersten
    `output_channels` Kanäle heraus.

    Wird benötigt, weil Interfaces wie die Behringer X-Serie
    immer mit ihrer vollen, festen Kanalzahl aufgenommen werden
    müssen (ALSA kennt dort keinen Modus mit weniger Kanälen).
    Die gewünschte, kleinere Kanalzahl wird deshalb erst hier in
    Software aus dem vollen Datenstrom herausgeschnitten.
    """

    BYTES_PER_SAMPLE = 4

    def __init__(
        self,
        input_channels: int,
        output_channels: int,
    ):

        self.input_channels = input_channels
        self.output_channels = output_channels

    def extract(self, data: bytes) -> bytes:
        """
        Extrahiert die gewünschten Kanäle aus einem Datenblock.
        """

        if self.output_channels >= self.input_channels:
            return data

        input_frame_size = (
            self.input_channels * self.BYTES_PER_SAMPLE
        )

        output_frame_size = (
            self.output_channels * self.BYTES_PER_SAMPLE
        )

        frame_count = len(data) // input_frame_size

        out = bytearray(frame_count * output_frame_size)

        for frame in range(frame_count):

            src_offset = frame * input_frame_size
            dst_offset = frame * output_frame_size

            out[dst_offset:dst_offset + output_frame_size] = (
                data[src_offset:src_offset + output_frame_size]
            )

        return bytes(out)
