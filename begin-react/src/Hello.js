import React from "react";

// function Hello(props) {
//     return <div style={{ color: props.color }}>안녕하세요 {props.name}</div>
// }

// 컴포넌트는 일종의 UI 조각. 함수형태나 클래스 형태로 작성 가능
// 비구조화 할당(구조 분해)
function Hello({ color, name, isSpecial }) {

    // JSX(Javascript XML)
    // { JSX 문법 { 객체리터럴 }}
    // return <div style={{ color }}>안녕하세요 { name }</div>
    return (
        // <div style={{ color }}>
        //     {/*삼항연산자 조건*/}
        //     {/*null, false, undefined -> 렌더링 x*/}
        //     {isSpecial ? <b>*</b> : null}
        //     안녕하세요 { name }
        // </div>

        // 단순 특정 조건건
       <div style={{ color }}>
            {/*삼항연산자 조건*/}
            {/*null, false, undefined -> 렌더링 x*/}
            {isSpecial ? <b>*</b> : null}
            안녕하세요 { name }
        </div>
    )
}

// defaultProps: 컴포넌트에 props를 지정하지 않았을 때 기본적으로 사용할 값 설정
Hello.defaultProps = {
    name: '이름없음'
}
export default Hello;