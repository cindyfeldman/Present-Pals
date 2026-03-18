import React from 'react';

const Bow = ({ className }) => (
  <svg className={className} viewBox="0 0 800 400" fill="none" xmlns="http://www.w3.org/2000/svg">
    <path d="M520 230C600 230 750 330 750 330C700 280 650 390 650 390C550 300 520 280 520 230Z" fill="white" stroke="black" strokeWidth="4"/>
    <path d="M280 230C200 230 50 330 50 330C100 280 150 390 150 390C250 300 280 280 280 230Z" fill="white" stroke="black" strokeWidth="4"/>
    <path d="M400 180C450 50 650 50 650 180C650 310 450 280 400 230" fill="white" stroke="black" strokeWidth="4"/>
    <path d="M400 180C350 50 150 50 150 180C150 310 350 280 400 230" fill="white" stroke="black" strokeWidth="4"/>
    <ellipse cx="400" cy="185" rx="55" ry="75" fill="white" stroke="black" strokeWidth="4"/>
  </svg>
);

export default Bow;