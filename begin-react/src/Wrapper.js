import React from "react";

// function Wrapper(props) {
//     const style = {
//         border: '2px solid black',
//         padding: '16px'
//     };
//
//     return (
//         <div style={style}>
//             {/*내부의 내용을 보여주게 하기 위해 props.children을 렌더링*/}
//             {props.children}
//         </div>
//     )
// }

function Wrapper({ children }) {
    const style = {
        border: '2px solid black',
        padding: '16px'
    };

    return (
        <div style={style}>
            {/*내부의 내용을 보여주게 하기 위해 props.children을 렌더링*/}
            {children}
        </div>
    )
}

export default Wrapper;