// import logo from './logo.svg';
import './App.css';
import Hello from "./Hello";
import Wrapper from "./Wrapper"

{/*<header className="App-header">*/}
{/*  <img src={logo} className="App-logo" alt="logo" />*/}
{/*  <p>*/}
{/*    Edit <code>src/App.js</code> and save to reload.*/}
{/*  </p>*/}
{/*  <a*/}
{/*    className="App-link"*/}
{/*    href="https://reactjs.org"*/}
{/*    target="_blank"*/}
{/*    rel="noopener noreferrer"*/}
{/*  >*/}
{/*    Learn React*/}
{/*  </a>*/}
{/*</header>*/}

function App() {
    // const name = "react";
    // const style = {
    //     backgroundColor: 'black',
    //     color: 'aqua',
    //     fontSize: 24,
    //     padding: '1rem'
    // }
  return (
    // <div className="App">
    //
    //   <div>
    //     <Hello // 주석 작성 가능
    //    />
    //     <div style={style}>{name}</div>
    //     <div className="gray-box"/>
    //   </div>
    // </div>
      <Wrapper>
          {/*조건부 렌더링: 특정 조건에 따라 다른 결과물 랜더링*/}
          <Hello name="react" color="red" isSpecial={true} />
          <Hello color="pink" />
      </Wrapper>

  );
}

export default App;
