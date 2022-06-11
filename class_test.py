
# class Test:
#     def __init__(self, num=0):
#         self.num = num
#
#     def test(self):
#         if self.num != 0:
#             return print(f'num : {self.num}')
#
#         else:
#             return print(f'num : {self.num}')
#
# a = Test(1)
# a.test()


class SomeClass:
    def __init__(self, num=0):
        self.num = num

    def test(self):
        if self.num:
            return self.num

        else:
            raise TypeError

while True:
    input_val = input('출력하고자 하는 숫자 : ')
    a = SomeClass(int(input_val))
    
    # a.test -> 리턴값만 출력
    print(f'out : {a.test()}')
