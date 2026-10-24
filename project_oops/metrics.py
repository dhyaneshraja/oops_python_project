# metrics.py - reads the finished packets and calculates performance numbers


class Metrics:
    def __init__(self, packets):
        self.packets = packets

    @staticmethod
    def percentage(part, total):
        if total == 0:
            return 0.0
        return part * 100 / total

    # *numbers lets the same method accept any number of arguments
    @staticmethod
    def average(*numbers):
        if len(numbers) == 0:
            return 0.0
        return sum(numbers) / len(numbers)

    def delivered(self):
        result = []
        for p in self.packets:
            if p.is_delivered():
                result.append(p)
        return result

    def dropped(self):
        result = []
        for p in self.packets:
            if p.is_dropped():
                result.append(p)
        return result

    def delivery_percent(self):
        return Metrics.percentage(len(self.delivered()), len(self.packets))

    def loss_percent(self):
        return Metrics.percentage(len(self.dropped()), len(self.packets))

    def average_hops(self):
        return Metrics.average(*[p.hop_count() for p in self.delivered()])

    def average_latency(self):
        return Metrics.average(*[p.delay for p in self.delivered()])

    def drop_reasons(self):
        reasons = {}                        # dictionary: reason -> how many
        for p in self.dropped():
            reasons[p.drop_reason] = reasons.get(p.drop_reason, 0) + 1
        return reasons

    def report(self, title):
        text = "--- " + title + " ---\n"
        text += "  Packets sent      : " + str(len(self.packets)) + "\n"
        text += "  Delivered         : " + str(len(self.delivered())) + "\n"
        text += "  Dropped           : " + str(len(self.dropped())) + "\n"
        text += "  Delivery %        : " + str(round(self.delivery_percent(), 1)) + "\n"
        text += "  Loss %            : " + str(round(self.loss_percent(), 1)) + "\n"
        text += "  Average hop count : " + str(round(self.average_hops(), 2)) + "\n"
        text += "  Average latency   : " + str(round(self.average_latency(), 2)) + " ms\n"
        reasons = self.drop_reasons()
        if reasons:
            text += "  Drop reasons      : " + str(reasons) + "\n"
        return text
